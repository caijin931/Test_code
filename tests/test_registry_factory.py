from __future__ import annotations

from testcode.config.settings import AppSettings
from testcode.providers.registry import ProviderRegistry


def test_provider_registry_from_settings_builds_clients() -> None:
    settings = AppSettings.from_mapping(
        {
            "coze": {"access_token": "coze-token", "base_url": "https://coze.example.com", "timeout_seconds": 11},
            "dify": {"api_key": "dify-key", "base_url": "https://dify.example.com", "timeout_seconds": 12},
            "n8n": {"base_url": "https://n8n.example.com/api", "timeout_seconds": 13},
        }
    )

    registry = ProviderRegistry.from_settings(settings)

    assert registry.coze.access_token == "coze-token"
    assert registry.coze.base_url == "https://coze.example.com"
    assert registry.dify.api_key == "dify-key"
    assert registry.n8n.base_url == "https://n8n.example.com/api"
