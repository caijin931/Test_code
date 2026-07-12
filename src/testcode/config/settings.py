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

        def _pick(env_val: Any, yaml_val: Any) -> Any:
            """Pick env_val if it is non-empty, otherwise fall back to yaml_val."""
            if env_val is None:
                return yaml_val
            s = str(env_val).strip()
            return s if s else yaml_val

        return cls.from_mapping(
            {
                "coze": {
                    "access_token": _pick(overrides.coze.access_token, base.coze.access_token),
                    "bot_id": _pick(overrides.coze.bot_id, base.coze.bot_id),
                    "base_url": _pick(overrides.coze.base_url, base.coze.base_url) or "https://api.coze.com",
                    "timeout_seconds": _pick(overrides.coze.timeout_seconds, base.coze.timeout_seconds) or 30.0,
                },
                "dify": {
                    "api_key": _pick(overrides.dify.api_key, base.dify.api_key),
                    "base_url": _pick(overrides.dify.base_url, base.dify.base_url) or "https://api.dify.ai",
                    "timeout_seconds": _pick(overrides.dify.timeout_seconds, base.dify.timeout_seconds) or 30.0,
                    "cache_enabled": overrides.dify.cache_enabled if overrides.dify.cache_enabled is not None else base.dify.cache_enabled,
                    "cache_directory": _pick(overrides.dify.cache_directory, base.dify.cache_directory) or ".cache/dify",
                    "cache_ttl_seconds": _pick(overrides.dify.cache_ttl_seconds, base.dify.cache_ttl_seconds) or 86400,
                    "cache_backend": _pick(overrides.dify.cache_backend, base.dify.cache_backend) or "file",
                    "cache_redis_url": _pick(overrides.dify.cache_redis_url, base.dify.cache_redis_url),
                    "cache_redis_prefix": _pick(overrides.dify.cache_redis_prefix, base.dify.cache_redis_prefix) or "testcode:dify",
                },
                "n8n": {
                    "base_url": _pick(overrides.n8n.base_url, base.n8n.base_url),
                    "timeout_seconds": _pick(overrides.n8n.timeout_seconds, base.n8n.timeout_seconds) or 30.0,
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
                    "bot_id": os.getenv(f"{prefix}COZE_BOT_ID", ""),
                    "base_url": os.getenv(f"{prefix}COZE_BASE_URL", ""),
                    "timeout_seconds": os.getenv(f"{prefix}COZE_TIMEOUT_SECONDS", ""),
                },
                "dify": {
                    "api_key": os.getenv(f"{prefix}DIFY_API_KEY", ""),
                    "base_url": os.getenv(f"{prefix}DIFY_BASE_URL", ""),
                    "timeout_seconds": os.getenv(f"{prefix}DIFY_TIMEOUT_SECONDS", ""),
                    "cache_enabled": os.getenv(f"{prefix}DIFY_CACHE_ENABLED", "true"),
                    "cache_directory": os.getenv(f"{prefix}DIFY_CACHE_DIRECTORY", ".cache/dify"),
                    "cache_ttl_seconds": os.getenv(f"{prefix}DIFY_CACHE_TTL_SECONDS", 86400),
                    "cache_backend": os.getenv(f"{prefix}DIFY_CACHE_BACKEND", "file"),
                    "cache_redis_url": os.getenv(f"{prefix}DIFY_CACHE_REDIS_URL", ""),
                    "cache_redis_prefix": os.getenv(f"{prefix}DIFY_CACHE_REDIS_PREFIX", "testcode:dify"),
                },
                "n8n": {
                    "base_url": os.getenv(f"{prefix}N8N_BASE_URL", ""),
                    "timeout_seconds": os.getenv(f"{prefix}N8N_TIMEOUT_SECONDS", ""),
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
                bot_id=str(coze.get("bot_id", "")),
                base_url=str(coze.get("base_url", "https://api.coze.com")),
                timeout_seconds=_safe_float(coze.get("timeout_seconds", 30.0)),
            ),
            dify=DifySettings(
                api_key=str(dify.get("api_key", "")),
                base_url=str(dify.get("base_url", "https://api.dify.ai")),
                timeout_seconds=_safe_float(dify.get("timeout_seconds", 30.0)),
                cache_enabled=str(dify.get("cache_enabled", "true")).lower() not in {"0", "false", "no"},
                cache_directory=str(dify.get("cache_directory", ".cache/dify")),
                cache_ttl_seconds=int(dify.get("cache_ttl_seconds", 86400)),
                cache_backend=str(dify.get("cache_backend", "file")),
                cache_redis_url=str(dify.get("cache_redis_url", "")),
                cache_redis_prefix=str(dify.get("cache_redis_prefix", "testcode:dify")),
            ),
            n8n=N8nSettings(
                base_url=str(n8n.get("base_url", "")),
                timeout_seconds=_safe_float(n8n.get("timeout_seconds", 30.0)),
            ),
        )

    def create_n8n_client(self) -> N8nClient:
        return N8nClient(base_url=self.n8n.base_url, timeout=self.n8n.timeout_seconds)


def _safe_float(value: Any, default: float = 30.0) -> float:
    """Convert value to float, falling back to default for empty/None strings."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
