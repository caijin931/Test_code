from __future__ import annotations

import httpx

from testcode.adapters.coze import CozeClient
from testcode.adapters.dify import DifyClient
from testcode.providers.registry import ProviderRegistry
from testcode.workflow import WorkflowOrchestrator


class StubTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_run_coze_then_dify_chains_outputs() -> None:
    def coze_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat"
        return httpx.Response(200, json={"code": 0, "messages": [{"role": "assistant", "content": "coze answer"}], "usage": {"tokens": 3}})

    def dify_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat-messages"
        body = request.read().decode()
        assert "coze answer" in body
        return httpx.Response(200, json={"answer": "dify final", "usage": {"tokens": 7}})

    coze_http = httpx.Client(transport=StubTransport(coze_handler), base_url="https://api.coze.com")
    dify_http = httpx.Client(transport=StubTransport(dify_handler), base_url="https://api.dify.ai")

    registry = ProviderRegistry(
        coze=CozeClient(access_token="token", client=coze_http),
        dify=DifyClient(api_key="key", client=dify_http),
    )

    orchestrator = WorkflowOrchestrator(registry=registry)
    result = orchestrator.run_coze_then_dify(
        coze_bot_id="bot",
        coze_user_id="user",
        coze_query="search the web",
        dify_user="user",
        dify_inputs={"topic": "automation"},
    )

    assert result["coze"].content == "coze answer"
    assert result["dify"].content == "dify final"
    assert result["dify"].messages[0].content == "dify final"
