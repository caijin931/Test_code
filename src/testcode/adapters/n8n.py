from __future__ import annotations

from dataclasses import dataclass, field
from time import sleep
from typing import Any

import httpx

from testcode.models.n8n import N8nTriggerResult


class N8nAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, raw: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw = raw or {}


@dataclass(slots=True)
class N8nClient:
    base_url: str = ""
    timeout: float = 30.0
    client: httpx.Client | None = None
    _client: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = self.client or httpx.Client(timeout=self.timeout)

    def close(self) -> None:
        if self.client is None:
            self._client.close()

    def trigger_workflow(self, webhook_url: str, payload: dict[str, Any]) -> N8nTriggerResult:
        try:
            response = self._client.post(webhook_url, json=payload)
        except httpx.TimeoutException as exc:
            raise N8nAPIError(504, "n8n webhook request timed out") from exc
        except httpx.RequestError as exc:
            raise N8nAPIError(502, f"n8n webhook request failed: {exc}") from exc

        data = self._parse_response(response)
        execution_id = str(data.get("executionId") or data.get("execution_id") or data.get("id") or "") or None
        status = str(data.get("status") or data.get("data", {}).get("status") or ("success" if response.is_success else "failed"))
        return N8nTriggerResult(workflow_url=webhook_url, execution_id=execution_id, status=status, result=data.get("data") or data, raw=data)

    def wait_for_completion(
        self,
        execution_id: str,
        *,
        poll_interval_seconds: float = 2.0,
        timeout_seconds: float = 60.0,
        terminal_statuses: tuple[str, ...] = ("success", "failed", "error", "canceled", "cancelled"),
    ) -> N8nTriggerResult:
        elapsed = 0.0
        latest = self.check_workflow_status(execution_id)
        while latest.status.lower() not in terminal_statuses and elapsed < timeout_seconds:
            sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds
            latest = self.check_workflow_status(execution_id)
        return latest

    def check_workflow_status(self, execution_id: str) -> N8nTriggerResult:
        response = self._client.get(f"{self.base_url.rstrip('/')}/executions/{execution_id}")
        data = self._parse_response(response)
        status = str(data.get("status") or data.get("data", {}).get("status") or "unknown")
        return N8nTriggerResult(workflow_url=f"{self.base_url.rstrip('/')}/executions/{execution_id}", execution_id=execution_id, status=status, result=data.get("data") or data, raw=data)

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        text = response.text.strip()
        if not text:
            if response.status_code >= 400:
                raise N8nAPIError(response.status_code, "n8n request failed with empty response body")
            return {"status": "success", "raw_text": ""}

        try:
            data = response.json()
        except ValueError:
            if response.status_code >= 400:
                raise N8nAPIError(response.status_code, "n8n request failed", raw={"raw_text": text})
            return {"status": "success", "raw_text": text}

        if response.status_code >= 400:
            message = data.get("message") or data.get("error") or "n8n request failed"
            raise N8nAPIError(response.status_code, message, raw=data)
        return data
