from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from testcode.models.provider_result import ProviderMessage, ProviderResult
from testcode.providers.base import ProviderAdapter


class DifyAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, raw: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw = raw or {}


@dataclass(slots=True)
class DifyClient(ProviderAdapter):
    api_key: str
    base_url: str = "https://api.dify.ai"
    timeout: float = 30.0
    client: httpx.Client | None = None

    def __post_init__(self) -> None:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        self._client = self.client or httpx.Client(base_url=self.base_url, timeout=self.timeout, headers=headers)

    def close(self) -> None:
        if self.client is None:
            self._client.close()

    def chat(self, query: str, user: str, inputs: dict[str, Any] | None = None) -> ProviderResult:
        response = self._client.post("/v1/chat-messages", json={"query": query, "user": user, "inputs": inputs or {}})
        return self._normalize(self._parse(response), kind="chat")

    def run_workflow(self, workflow_id: str, parameters: dict[str, Any]) -> ProviderResult:
        response = self._client.post("/v1/workflows/run", json={"workflow_id": workflow_id, "inputs": parameters})
        return self._normalize(self._parse(response), kind="workflow")

    def _parse(self, response: httpx.Response) -> dict[str, Any]:
        data = response.json()
        if response.status_code >= 400:
            raise DifyAPIError(response.status_code, data.get("message", "Dify API request failed"), raw=data)
        return data

    def _normalize(self, data: dict[str, Any], kind: str) -> ProviderResult:
        answer = str(data.get("answer") or data.get("data", {}).get("answer") or "")
        messages = [ProviderMessage(role="assistant", content=answer, raw=data)] if answer else []
        return ProviderResult(provider="dify", kind=kind, content=answer, messages=messages, usage=data.get("usage") or {}, raw=data)
