from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from testcode.models.provider_result import ProviderMessage, ProviderResult
from testcode.providers.base import ProviderAdapter


class CozeAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, code: str | None = None, raw: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.raw = raw or {}


@dataclass(slots=True)
class CozeClient(ProviderAdapter):
    access_token: str
    base_url: str = "https://api.coze.com"
    timeout: float = 30.0
    client: httpx.Client | None = None

    def __post_init__(self) -> None:
        self._client = self.client or httpx.Client(base_url=self.base_url, timeout=self.timeout, headers=self._headers)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    def close(self) -> None:
        if self.client is None:
            self._client.close()

    def chat(self, bot_id: str, user_id: str, query: str, additional_params: dict[str, Any] | None = None) -> ProviderResult:
        payload: dict[str, Any] = {"bot_id": bot_id, "user_id": user_id, "query": query}
        if additional_params:
            payload.update(additional_params)
        response = self._client.post("/v1/chat", json=payload)
        return self._normalize_result(self._parse_response(response), kind="chat")

    def run_workflow(self, workflow_id: str, parameters: dict[str, Any]) -> ProviderResult:
        response = self._client.post("/v1/workflow/run", json={"workflow_id": workflow_id, "parameters": parameters})
        return self._normalize_result(self._parse_response(response), kind="workflow")

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
        messages: list[ProviderMessage] = []
        content = ""
        for item in data.get("messages", []) or []:
            message_content = str(item.get("content") or "")
            if not content and message_content:
                content = message_content
            messages.append(ProviderMessage(role=str(item.get("role") or "assistant"), content=message_content, raw=item))
        if not content:
            content = str(data.get("data", {}).get("content") or data.get("answer") or data.get("result") or "")
        return ProviderResult(provider="coze", kind=kind, content=content, messages=messages, usage=data.get("usage") or {}, raw=data)
