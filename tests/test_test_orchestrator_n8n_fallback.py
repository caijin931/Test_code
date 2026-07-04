from __future__ import annotations

import httpx

from testcode.adapters.coze import CozeClient
from testcode.adapters.dify import DifyClient
from testcode.adapters.n8n import N8nClient
from testcode.models import TestRequirement
from testcode.providers.registry import ProviderRegistry
from testcode.test_orchestrator import TestOrchestrator


def test_execute_test_flow_falls_back_when_n8n_returns_text() -> None:
    def n8n_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"accepted")

    n8n_http = httpx.Client(transport=httpx.MockTransport(n8n_handler), base_url="https://n8n.example.com")
    registry = ProviderRegistry(
        coze=CozeClient(access_token="token", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"messages": []})), base_url="https://api.coze.com")),
        dify=DifyClient(api_key="key", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"answer": "ok"})), base_url="https://api.dify.ai")),
        n8n=N8nClient(base_url="https://n8n.example.com", client=n8n_http),
    )

    orchestrator = TestOrchestrator(registry=registry)
    result = orchestrator.execute_test_flow(TestRequirement(request_id="req-1", requirement="测试登录功能"), "https://n8n.example.com/webhook/test")

    assert result["execution_result"].status in {"success", "deferred"}
