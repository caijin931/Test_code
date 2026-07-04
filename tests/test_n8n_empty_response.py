from __future__ import annotations

import httpx

from testcode.adapters.n8n import N8nClient


class StubTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_trigger_workflow_accepts_empty_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    client = httpx.Client(transport=StubTransport(handler), base_url="https://n8n.example.com")
    n8n = N8nClient(client=client)

    result = n8n.trigger_workflow("https://n8n.example.com/webhook/test", {"hello": "world"})

    assert result.status == "success"
    assert result.raw["status"] == "success"


def test_trigger_workflow_accepts_plain_text_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"accepted")

    client = httpx.Client(transport=StubTransport(handler), base_url="https://n8n.example.com")
    n8n = N8nClient(client=client)

    result = n8n.trigger_workflow("https://n8n.example.com/webhook/test", {"hello": "world"})

    assert result.status == "success"
    assert result.raw["raw_text"] == "accepted"
