from __future__ import annotations

from pathlib import Path

from testcode.cache import DifyCache
from testcode.models.provider_result import ProviderResult


def test_dify_cache_cleanup_removes_expired_entries(tmp_path: Path) -> None:
    cache = DifyCache(directory=tmp_path, ttl_seconds=1)
    result = ProviderResult(provider="dify", kind="chat", content="hello", raw={"answer": "hello"})

    cache.set("chat", {"query": "hello", "user": "u", "inputs": {}}, result)
    removed = cache.cleanup(now=10_000_000_000)

    assert removed >= 1
    assert not any(tmp_path.glob("*.json"))


def test_dify_cache_cleanup_keeps_fresh_entries(tmp_path: Path) -> None:
    cache = DifyCache(directory=tmp_path, ttl_seconds=3600)
    result = ProviderResult(provider="dify", kind="chat", content="hello", raw={"answer": "hello"})

    cache.set("chat", {"query": "hello", "user": "u", "inputs": {}}, result)
    removed = cache.cleanup(now=1)

    assert removed == 0
    assert any(tmp_path.glob("*.json"))
