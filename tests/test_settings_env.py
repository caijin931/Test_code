from __future__ import annotations

from testcode.config.settings import AppSettings


def test_app_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TESTCODE_COZE_ACCESS_TOKEN", "env-coze")
    monkeypatch.setenv("TESTCODE_DIFY_API_KEY", "env-dify")
    monkeypatch.setenv("TESTCODE_N8N_BASE_URL", "https://n8n.env/api")

    settings = AppSettings.from_env()

    assert settings.coze.access_token == "env-coze"
    assert settings.dify.api_key == "env-dify"
    assert settings.n8n.base_url == "https://n8n.env/api"


def test_env_defaults_do_not_break() -> None:
    settings = AppSettings.from_env(prefix="MISSING_")

    assert settings.coze.base_url == "https://api.coze.com"
    assert settings.dify.base_url == "https://api.dify.ai"
