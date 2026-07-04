from __future__ import annotations

from testcode.config.settings import AppSettings


def test_dify_cache_settings_from_mapping() -> None:
    settings = AppSettings.from_mapping(
        {
            "dify": {
                "api_key": "key",
                "cache_enabled": "false",
                "cache_directory": ".cache/custom",
                "cache_ttl_seconds": 123,
            }
        }
    )

    assert settings.dify.api_key == "key"
    assert settings.dify.cache_enabled is False
    assert settings.dify.cache_directory == ".cache/custom"
    assert settings.dify.cache_ttl_seconds == 123
