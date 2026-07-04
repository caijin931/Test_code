from __future__ import annotations

import httpx

from testcode.adapters.n8n import N8nClient


class StubTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_wait_for_completion_polls_until_terminal_status(monkeypatch) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(200, json={"status": "running", "data": {"step": 1}})
        return httpx.Response(200, json={"status": "success", "data": {"step": 2}})

    client = httpx.Client(transport=StubTransport(handler), base_url="https://n8n.example.com/api")
    n8n = N8nClient(base_url="https://n8n.example.com/api", client=client)

    monkeypatch.setattr("testcode.adapters.n8n.sleep", lambda _: None)
    result = n8n.wait_for_completion("exec-1", poll_interval_seconds=0.01, timeout_seconds=0.05)

    assert result.status == "success"
    assert result.result["step"] == 2
    assert calls["count"] >= 2
