from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
from time import time
from typing import Any

from testcode.adapters.dify import DifyClient
from testcode.models.provider_result import ProviderResult


@dataclass(slots=True)
class DifyCacheEntry:
    created_at: float
    ttl_seconds: int
    payload: dict[str, Any]

    def expired(self, now: float | None = None) -> bool:
        current = time() if now is None else now
        return (current - self.created_at) > self.ttl_seconds


@dataclass(slots=True)
class DifyCache:
    directory: Path
    ttl_seconds: int = 86400
    enabled: bool = True
    _memory_index: dict[str, DifyCacheEntry] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def _key(self, kind: str, payload: dict[str, Any]) -> str:
        digest = sha256(
            json.dumps({"kind": kind, "payload": payload}, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return digest

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, kind: str, payload: dict[str, Any]) -> ProviderResult | None:
        if not self.enabled:
            return None
        key = self._key(kind, payload)
        entry = self._memory_index.get(key)
        if entry and not entry.expired():
            return self._to_result(entry.payload)
        file_path = self._path(key)
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        entry = DifyCacheEntry(created_at=float(data["created_at"]), ttl_seconds=int(data["ttl_seconds"]), payload=data["payload"])
        if entry.expired():
            return None
        self._memory_index[key] = entry
        return self._to_result(entry.payload)

    def set(self, kind: str, payload: dict[str, Any], result: ProviderResult) -> None:
        if not self.enabled:
            return
        key = self._key(kind, payload)
        entry_payload = result.raw or {
            "provider": result.provider,
            "kind": result.kind,
            "content": result.content,
            "messages": [message.__dict__ for message in result.messages],
            "usage": result.usage,
            "raw": result.raw,
        }
        entry = DifyCacheEntry(created_at=time(), ttl_seconds=self.ttl_seconds, payload=entry_payload)
        self._memory_index[key] = entry
        self._path(key).write_text(
            json.dumps({"created_at": entry.created_at, "ttl_seconds": entry.ttl_seconds, "payload": entry.payload}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def cleanup(self, now: float | None = None) -> int:
        if not self.enabled:
            return 0
        current = time() if now is None else now
        removed = 0
        for file_path in self.directory.glob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                entry = DifyCacheEntry(created_at=float(data["created_at"]), ttl_seconds=int(data["ttl_seconds"]), payload=data["payload"])
                if entry.expired(now=current):
                    file_path.unlink(missing_ok=True)
                    removed += 1
            except (OSError, KeyError, ValueError, json.JSONDecodeError):
                file_path.unlink(missing_ok=True)
                removed += 1
        self._memory_index = {
            key: entry for key, entry in self._memory_index.items() if not entry.expired(now=current)
        }
        return removed

    def _to_result(self, payload: dict[str, Any]) -> ProviderResult:
        return ProviderResult(
            provider=str(payload.get("provider", "dify")),
            kind=str(payload.get("kind", "chat")),
            content=str(payload.get("content", "")),
            messages=[],
            usage=dict(payload.get("usage") or {}),
            raw=dict(payload.get("raw") or payload),
        )


@dataclass(slots=True)
class RedisDifyCache:
    redis_client: Any
    prefix: str = "testcode:dify"
    ttl_seconds: int = 86400

    def _key(self, kind: str, payload: dict[str, Any]) -> str:
        digest = sha256(
            json.dumps({"kind": kind, "payload": payload}, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return f"{self.prefix}:{digest}"

    def get(self, kind: str, payload: dict[str, Any]) -> ProviderResult | None:
        raw = self.redis_client.get(self._key(kind, payload))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return ProviderResult(
            provider=str(data.get("provider", "dify")),
            kind=str(data.get("kind", kind)),
            content=str(data.get("content", "")),
            messages=[],
            usage=dict(data.get("usage") or {}),
            raw=dict(data.get("raw") or data),
        )

    def set(self, kind: str, payload: dict[str, Any], result: ProviderResult) -> None:
        key = self._key(kind, payload)
        data = {
            "provider": result.provider,
            "kind": result.kind,
            "content": result.content,
            "usage": result.usage,
            "raw": result.raw,
        }
        self.redis_client.setex(key, self.ttl_seconds, json.dumps(data, ensure_ascii=False))


@dataclass(slots=True)
class CachedDifyClient:
    client: DifyClient
    cache: Any

    def chat(self, query: str, user: str, inputs: dict[str, Any] | None = None) -> ProviderResult:
        payload = {"query": query, "user": user, "inputs": inputs or {}}
        cached = self.cache.get("chat", payload)
        if cached is not None:
            return cached
        result = self.client.chat(query=query, user=user, inputs=inputs)
        self.cache.set("chat", payload, result)
        return result

    def run_workflow(self, workflow_id: str, parameters: dict[str, Any]) -> ProviderResult:
        payload = {"workflow_id": workflow_id, "parameters": parameters}
        cached = self.cache.get("workflow", payload)
        if cached is not None:
            return cached
        result = self.client.run_workflow(workflow_id=workflow_id, parameters=parameters)
        self.cache.set("workflow", payload, result)
        return result
