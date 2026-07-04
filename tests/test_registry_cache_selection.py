from __future__ import annotations

from testcode.config.settings import AppSettings
from testcode.providers.registry import ProviderRegistry
from testcode.cache import CachedDifyClient


def test_registry_uses_file_cache_by_default(tmp_path) -> None:
    settings = AppSettings.from_mapping(
        {
            "coze": {"access_token": "token"},
            "dify": {"api_key": "key", "cache_directory": str(tmp_path)},
            "n8n": {"base_url": "https://n8n.example.com/api"},
        }
    )

    registry = ProviderRegistry.from_settings(settings)

    assert isinstance(registry.dify, CachedDifyClient)


def test_registry_can_disable_cache(tmp_path) -> None:
    settings = AppSettings.from_mapping(
        {
            "coze": {"access_token": "token"},
            "dify": {"api_key": "key", "cache_enabled": False, "cache_directory": str(tmp_path)},
            "n8n": {"base_url": "https://n8n.example.com/api"},
        }
    )

    registry = ProviderRegistry.from_settings(settings)

    assert not isinstance(registry.dify, CachedDifyClient)
