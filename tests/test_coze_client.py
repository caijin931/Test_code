from __future__ import annotations

import httpx
import pytest

from testcode.adapters.coze import CozeAPIError, CozeClient


class DummyTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_chat_normalizes_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "messages": [
                    {"role": "assistant", "content": "hello"},
                ],
                "usage": {"tokens": 12},
            },
        )

    client = CozeClient(access_token="token")
    with httpx.Client(transport=DummyTransport(handler), base_url="https://api.coze.com") as _:
        result = client._normalize_result({
            "code": 0,
            "messages": [{"role": "assistant", "content": "hello"}],
            "usage": {"tokens": 12},
        }, kind="chat")

    assert result.provider == "coze"
    assert result.kind == "chat"
    assert result.content == "hello"
    assert result.messages[0].role == "assistant"


def test_error_payload_raises_coze_error() -> None:
    client = CozeClient(access_token="token")
    response = httpx.Response(401, json={"code": "Unauthorized", "message": "invalid token"})

    with pytest.raises(CozeAPIError) as exc_info:
        client._parse_response(response)

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "Unauthorized"
