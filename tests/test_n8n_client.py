from __future__ import annotations

import httpx

from testcode.adapters.n8n import N8nClient


class StubTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_trigger_workflow_returns_execution_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/webhook/test"
        return httpx.Response(200, json={"executionId": "exec-1", "status": "running", "data": {"ok": True}})

    client = httpx.Client(transport=StubTransport(handler), base_url="https://n8n.example.com")
    n8n = N8nClient(client=client)

    result = n8n.trigger_workflow("https://n8n.example.com/webhook/test", {"hello": "world"})

    assert result.execution_id == "exec-1"
    assert result.status == "running"
    assert result.result["ok"] is True


def test_check_workflow_status_uses_api_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/executions/exec-1"
        return httpx.Response(200, json={"status": "success", "data": {"finished": True}})

    client = httpx.Client(transport=StubTransport(handler), base_url="https://n8n.example.com")
    n8n = N8nClient(base_url="https://n8n.example.com/api", client=client)

    result = n8n.check_workflow_status("exec-1")

    assert result.status == "success"
    assert result.result["finished"] is True
