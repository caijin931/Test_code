from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback for environments without PyYAML
    yaml = None

from testcode.adapters.n8n import N8nClient
from testcode.config.coze import CozeSettings


@dataclass(slots=True)
class DifySettings:
    api_key: str = ""
    base_url: str = "https://api.dify.ai"
    timeout_seconds: float = 30.0
    cache_enabled: bool = True
    cache_directory: str = ".cache/dify"
    cache_ttl_seconds: int = 86400
    cache_backend: str = "file"
    cache_redis_url: str = ""
    cache_redis_prefix: str = "testcode:dify"


@dataclass(slots=True)
class N8nSettings:
    base_url: str = ""
    timeout_seconds: float = 30.0


@dataclass(slots=True)
class AppSettings:
    coze: CozeSettings
    dify: DifySettings
    n8n: N8nSettings

    @classmethod
    def load(cls, path: str | Path | None = None, prefix: str = "TESTCODE_") -> "AppSettings":
        base = cls.from_yaml(path) if path is not None else cls.from_mapping({})
        overrides = cls.from_env(prefix=prefix)
        return cls.from_mapping(
            {
                "coze": {
                    "access_token": overrides.coze.access_token or base.coze.access_token,
                    "base_url": overrides.coze.base_url or base.coze.base_url,
                    "timeout_seconds": overrides.coze.timeout_seconds or base.coze.timeout_seconds,
                },
                "dify": {
                    "api_key": overrides.dify.api_key or base.dify.api_key,
                    "base_url": overrides.dify.base_url or base.dify.base_url,
                    "timeout_seconds": overrides.dify.timeout_seconds or base.dify.timeout_seconds,
                    "cache_enabled": overrides.dify.cache_enabled if overrides.dify.cache_enabled is not None else base.dify.cache_enabled,
                    "cache_directory": overrides.dify.cache_directory or base.dify.cache_directory,
                    "cache_ttl_seconds": overrides.dify.cache_ttl_seconds or base.dify.cache_ttl_seconds,
                    "cache_backend": overrides.dify.cache_backend or base.dify.cache_backend,
                    "cache_redis_url": overrides.dify.cache_redis_url or base.dify.cache_redis_url,
                    "cache_redis_prefix": overrides.dify.cache_redis_prefix or base.dify.cache_redis_prefix,
                },
                "n8n": {
                    "base_url": overrides.n8n.base_url or base.n8n.base_url,
                    "timeout_seconds": overrides.n8n.timeout_seconds or base.n8n.timeout_seconds,
                },
            }
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AppSettings":
        raw_text = Path(path).read_text(encoding="utf-8")
        if yaml is not None:
            data = yaml.safe_load(raw_text) or {}
        else:
            data = _parse_simple_yaml(raw_text)
        return cls.from_mapping(data)

    @classmethod
    def from_env(cls, prefix: str = "TESTCODE_") -> "AppSettings":
        return cls.from_mapping(
            {
                "coze": {
                    "access_token": os.getenv(f"{prefix}COZE_ACCESS_TOKEN", ""),
                    "base_url": os.getenv(f"{prefix}COZE_BASE_URL", "https://api.coze.com"),
                    "timeout_seconds": os.getenv(f"{prefix}COZE_TIMEOUT_SECONDS", 30.0),
                },
                "dify": {
                    "api_key": os.getenv(f"{prefix}DIFY_API_KEY", ""),
                    "base_url": os.getenv(f"{prefix}DIFY_BASE_URL", "https://api.dify.ai"),
                    "timeout_seconds": os.getenv(f"{prefix}DIFY_TIMEOUT_SECONDS", 30.0),
                    "cache_enabled": os.getenv(f"{prefix}DIFY_CACHE_ENABLED", "true"),
                    "cache_directory": os.getenv(f"{prefix}DIFY_CACHE_DIRECTORY", ".cache/dify"),
                    "cache_ttl_seconds": os.getenv(f"{prefix}DIFY_CACHE_TTL_SECONDS", 86400),
                    "cache_backend": os.getenv(f"{prefix}DIFY_CACHE_BACKEND", "file"),
                    "cache_redis_url": os.getenv(f"{prefix}DIFY_CACHE_REDIS_URL", ""),
                    "cache_redis_prefix": os.getenv(f"{prefix}DIFY_CACHE_REDIS_PREFIX", "testcode:dify"),
                },
                "n8n": {
                    "base_url": os.getenv(f"{prefix}N8N_BASE_URL", ""),
                    "timeout_seconds": os.getenv(f"{prefix}N8N_TIMEOUT_SECONDS", 30.0),
                },
            }
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AppSettings":
        coze = data.get("coze", {}) or {}
        dify = data.get("dify", {}) or {}
        n8n = data.get("n8n", {}) or {}
        return cls(
            coze=CozeSettings(
                access_token=str(coze.get("access_token", "")),
                base_url=str(coze.get("base_url", "https://api.coze.com")),
                timeout_seconds=float(coze.get("timeout_seconds", 30.0)),
            ),
            dify=DifySettings(
                api_key=str(dify.get("api_key", "")),
                base_url=str(dify.get("base_url", "https://api.dify.ai")),
                timeout_seconds=float(dify.get("timeout_seconds", 30.0)),
                cache_enabled=str(dify.get("cache_enabled", "true")).lower() not in {"0", "false", "no"},
                cache_directory=str(dify.get("cache_directory", ".cache/dify")),
                cache_ttl_seconds=int(dify.get("cache_ttl_seconds", 86400)),
                cache_backend=str(dify.get("cache_backend", "file")),
                cache_redis_url=str(dify.get("cache_redis_url", "")),
                cache_redis_prefix=str(dify.get("cache_redis_prefix", "testcode:dify")),
            ),
            n8n=N8nSettings(
                base_url=str(n8n.get("base_url", "")),
                timeout_seconds=float(n8n.get("timeout_seconds", 30.0)),
            ),
        )

    def create_n8n_client(self) -> N8nClient:
        return N8nClient(base_url=self.n8n.base_url, timeout=self.n8n.timeout_seconds)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    section: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.endswith(":"):
            key = line[:-1].strip()
            section = data.setdefault(key, {})
            continue
        if ":" in line and section is not None:
            key, value = line.strip().split(":", 1)
            section[key.strip()] = _coerce_scalar(value.strip().strip('"\''))
    return data


def _coerce_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value
