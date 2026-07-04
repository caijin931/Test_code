from __future__ import annotations

from pathlib import Path

from testcode.adapters.dify import DifyClient
from testcode.cache import CachedDifyClient, DifyCache
from testcode.models.provider_result import ProviderMessage, ProviderResult


class DummyDifyClient:
    def __init__(self):
        self.calls = 0

    def chat(self, query: str, user: str, inputs=None):
        self.calls += 1
        return ProviderResult(provider="dify", kind="chat", content="cached answer", messages=[ProviderMessage(role="assistant", content="cached answer")], raw={"answer": "cached answer"})

    def run_workflow(self, workflow_id: str, parameters: dict):
        self.calls += 1
        return ProviderResult(provider="dify", kind="workflow", content="workflow result", messages=[], raw={"answer": "workflow result"})


def test_dify_cache_hits_and_misses(tmp_path: Path) -> None:
    cache = DifyCache(directory=tmp_path, ttl_seconds=60)
    client = DummyDifyClient()
    cached = CachedDifyClient(client=client, cache=cache)

    first = cached.chat(query="hello", user="u")
    second = cached.chat(query="hello", user="u")

    assert first.content == "cached answer"
    assert second.content == "cached answer"
    assert client.calls == 1


def test_dify_cache_expiry(tmp_path: Path) -> None:
    cache = DifyCache(directory=tmp_path, ttl_seconds=0)
    client = DummyDifyClient()
    cached = CachedDifyClient(client=client, cache=cache)

    cached.chat(query="hello", user="u")
    cached.chat(query="hello", user="u")

    assert client.calls == 2
