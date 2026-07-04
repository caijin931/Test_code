from __future__ import annotations

from testcode.cache.dify_cache import RedisDifyCache
from testcode.models.provider_result import ProviderResult


class DummyRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value


def test_redis_cache_roundtrip() -> None:
    redis = DummyRedis()
    cache = RedisDifyCache(redis_client=redis)
    result = ProviderResult(provider="dify", kind="chat", content="hello", raw={"answer": "hello"})

    cache.set("chat", {"query": "hello", "user": "u", "inputs": {}}, result)
    cached = cache.get("chat", {"query": "hello", "user": "u", "inputs": {}})

    assert cached is not None
    assert cached.content == "hello"
