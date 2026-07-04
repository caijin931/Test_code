from __future__ import annotations

import httpx

from testcode.adapters.coze import CozeClient
from testcode.adapters.dify import DifyClient
from testcode.providers.registry import ProviderRegistry


class StubTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_registry_returns_matching_provider() -> None:
    coze_http = httpx.Client(transport=StubTransport(lambda request: httpx.Response(200, json={"code": 0, "messages": []})), base_url="https://api.coze.com")
    dify_http = httpx.Client(transport=StubTransport(lambda request: httpx.Response(200, json={"answer": "ok"})), base_url="https://api.dify.ai")

    registry = ProviderRegistry(
        coze=CozeClient(access_token="token", client=coze_http),
        dify=DifyClient(api_key="key", client=dify_http),
    )

    assert registry.get("coze") is registry.coze
    assert registry.get("dify") is registry.dify
