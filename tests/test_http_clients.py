from __future__ import annotations

import httpx

from testcode.adapters.coze import CozeClient
from testcode.adapters.dify import DifyClient


class StubTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_coze_client_uses_injected_http_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer token"
        assert request.url.path == "/v1/chat"
        return httpx.Response(200, json={"code": 0, "messages": [{"role": "assistant", "content": "ok"}]})

    client = httpx.Client(transport=StubTransport(handler), base_url="https://api.coze.com")
    coze = CozeClient(access_token="token", client=client)
    result = coze.chat(bot_id="bot", user_id="u", query="hello")

    assert result.provider == "coze"
    assert result.content == "ok"
    coze.close()


def test_dify_client_normalizes_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat-messages"
        return httpx.Response(200, json={"answer": "hi from dify", "usage": {"tokens": 9}})

    client = httpx.Client(transport=StubTransport(handler), base_url="https://api.dify.ai")
    dify = DifyClient(api_key="key", client=client)
    result = dify.chat(query="hello", user="u")

    assert result.provider == "dify"
    assert result.content == "hi from dify"
    assert result.messages[0].content == "hi from dify"
    dify.close()
