from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import time

import httpx

from testcode.models.provider_result import ProviderMessage, ProviderResult
from testcode.providers.base import ProviderAdapter


class CozeAPIError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        message: str,
        code: str | None = None,
        raw: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.raw = raw or {}


@dataclass(slots=True)
class CozeClient(ProviderAdapter):
    access_token: str
    bot_id: str = ""
    base_url: str = "https://api.coze.com"
    timeout: float = 30.0
    client: httpx.Client | None = None

    def __post_init__(self) -> None:
        self._client = self.client or httpx.Client(
            base_url=self.base_url, timeout=self.timeout, headers=self._headers
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    def close(self) -> None:
        if self.client is None:
            self._client.close()

    # ------------------------------------------------------------------
    # Coze v3 Chat API — create, poll, retrieve
    # ------------------------------------------------------------------

    def chat(
        self,
        bot_id: str,
        user_id: str,
        query: str,
        additional_params: dict[str, Any] | None = None,
    ) -> ProviderResult:
        """Send a chat message via Coze v3 API with polling for completion."""
        payload: dict[str, Any] = {
            "bot_id": bot_id,
            "user_id": user_id,
            "additional_messages": [
                {"role": "user", "content": query, "content_type": "text"}
            ],
            "stream": False,
            "auto_save_history": True,
        }
        if additional_params:
            payload.update(additional_params)

        # Step 1: create chat
        response = self._client.post("/v3/chat", json=payload)
        data = self._parse_response(response)
        chat_data = data.get("data", data)
        chat_id = chat_data.get("id") or chat_data.get("chat_id", "")
        conversation_id = chat_data.get("conversation_id") or chat_data.get("conversation_id", "")

        if not chat_id:
            # May have completed synchronously
            return self._normalize_result(data, kind="chat")

        # Step 2: poll for completion via GET
        max_attempts = int(self.timeout)
        for attempt in range(max_attempts):
            time.sleep(1.0)
            poll_resp = self._client.get(
                "/v3/chat/retrieve",
                params={"chat_id": chat_id, "conversation_id": conversation_id},
            )
            poll_data = self._parse_response(poll_resp)
            chat_info = poll_data.get("data", poll_data)
            status = (
                chat_info.get("status")
                or chat_info.get("chat_status")
                or ""
            ).lower()

            if status == "completed":
                # Step 3: fetch the actual messages (coze.cn requires separate call)
                return self._fetch_messages(chat_id, conversation_id)
            elif status in ("failed", "cancelled", "error"):
                err_msg = (
                    chat_info.get("error_message")
                    or chat_info.get("error")
                    or f"Chat {status}"
                )
                raise CozeAPIError(500, str(err_msg), raw=poll_data)

        raise CozeAPIError(
            408,
            f"Chat timed out after {max_attempts}s",
            code="timeout",
            raw={"chat_id": chat_id},
        )

    # ------------------------------------------------------------------
    # Coze v3 Workflow API
    # ------------------------------------------------------------------

    def run_workflow(self, workflow_id: str, parameters: dict[str, Any]) -> ProviderResult:
        """Run a Coze workflow via v3 API."""
        response = self._client.post(
            "/v3/workflow/run",
            json={"workflow_id": workflow_id, "parameters": parameters},
        )
        return self._normalize_result(self._parse_response(response), kind="workflow")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _fetch_messages(self, chat_id: str, conversation_id: str) -> ProviderResult:
        """Fetch message list after chat has completed."""
        msg_resp = self._client.get(
            "/v3/chat/message/list",
            params={"chat_id": chat_id, "conversation_id": conversation_id},
        )
        msg_data = self._parse_response(msg_resp)
        return self._normalize_result(msg_data, kind="chat")

    # ------------------------------------------------------------------

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise CozeAPIError(response.status_code, "Coze API returned invalid JSON") from exc
        if response.status_code >= 400:
            error = data.get("error") or data
            code = str(error.get("code") or error.get("error_code") or response.status_code)
            message = error.get("message") or error.get("msg") or "Coze API request failed"
            raise CozeAPIError(response.status_code, message, code=code, raw=data)
        if isinstance(data, dict) and data.get("code") not in (None, 0, "0", "success"):
            code = str(data.get("code"))
            message = data.get("msg") or data.get("message") or "Coze API request failed"
            raise CozeAPIError(response.status_code, message, code=code, raw=data)
        return data

    def _normalize_result(self, data: dict[str, Any], kind: str) -> ProviderResult:
        """Normalize v3 API response into a ProviderResult.

        Handles both:
        - retrieve response: data.messages is a list of message objects
        - message/list response: data is a flat list of message objects
        """
        body = data.get("data", data)
        messages: list[ProviderMessage] = []
        content = ""

        # Handle flat list (from /v3/chat/message/list)
        if isinstance(body, list):
            raw_messages = body
        else:
            raw_messages = body.get("messages", []) or []

        for item in raw_messages:
            item_role = str(item.get("role") or "assistant")
            item_content = str(item.get("content") or "")
            if not content and item_content and item_role in ("assistant", "bot"):
                content = item_content
            messages.append(
                ProviderMessage(role=item_role, content=item_content, raw=item)
            )

        if not content:
            content = str(
                body.get("answer")
                or body.get("result")
                or body.get("content")
                or ""
            )

        return ProviderResult(
            provider="coze",
            kind=kind,
            content=content,
            messages=messages,
            usage=data.get("usage") or {},
            raw=data,
        )
