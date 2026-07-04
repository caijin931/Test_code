from __future__ import annotations

from testcode.config.settings import AppSettings
from testcode.providers.registry import ProviderRegistry
from testcode.cache import CachedDifyClient


def test_registry_falls_back_to_file_cache_when_redis_is_unavailable(tmp_path) -> None:
    settings = AppSettings.from_mapping(
        {
            "coze": {"access_token": "token"},
            "dify": {
                "api_key": "key",
                "cache_backend": "redis",
                "cache_redis_url": "redis://localhost:6379/0",
                "cache_directory": str(tmp_path),
            },
            "n8n": {"base_url": "https://n8n.example.com/api"},
        }
    )

    registry = ProviderRegistry.from_settings(settings)

    assert isinstance(registry.dify, CachedDifyClient)


def test_registry_uses_file_cache_when_redis_not_configured(tmp_path) -> None:
    settings = AppSettings.from_mapping(
        {
            "coze": {"access_token": "token"},
            "dify": {"api_key": "key", "cache_backend": "redis", "cache_directory": str(tmp_path)},
            "n8n": {"base_url": "https://n8n.example.com/api"},
        }
    )

    registry = ProviderRegistry.from_settings(settings)

    assert isinstance(registry.dify, CachedDifyClient)
