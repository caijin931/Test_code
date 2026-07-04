from __future__ import annotations

import httpx

from testcode.adapters.coze import CozeClient
from testcode.adapters.dify import DifyClient
from testcode.adapters.n8n import N8nClient
from testcode.config.settings import AppSettings
from testcode.models import TestRequirement
from testcode.providers.registry import ProviderRegistry
from testcode.test_orchestrator import TestOrchestrator


class StubTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_execute_test_flow_returns_all_artifacts() -> None:
    def coze_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "messages": [{"role": "assistant", "content": "coze extra"}]})

    def dify_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answer": "dify ok"})

    def n8n_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"executionId": "exec-1", "status": "running", "data": {"ok": True}})
        return httpx.Response(200, json={"status": "success", "data": {"passed": 5, "failed": 0}})

    coze_http = httpx.Client(transport=StubTransport(coze_handler), base_url="https://api.coze.com")
    dify_http = httpx.Client(transport=StubTransport(dify_handler), base_url="https://api.dify.ai")
    n8n_http = httpx.Client(transport=StubTransport(n8n_handler), base_url="https://n8n.example.com/api")

    registry = ProviderRegistry(
        coze=CozeClient(access_token="token", client=coze_http),
        dify=DifyClient(api_key="key", client=dify_http),
        n8n=N8nClient(base_url="https://n8n.example.com/api", client=n8n_http),
    )

    orchestrator = TestOrchestrator(registry=registry)
    result = orchestrator.execute_test_flow(
        TestRequirement(request_id="req-1", requirement="测试登录功能", module_name="login"),
        "https://n8n.example.com/webhook/test",
    )

    assert result["test_cases"].cases[0].title.startswith("测试登录功能")
    assert result["enrichment"].datasource == "coze-plugin"
    assert result["execution_result"].status == "success"
    assert "测试流已完成" in result["report"].summary
