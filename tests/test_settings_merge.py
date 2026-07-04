from __future__ import annotations

from pathlib import Path

from testcode.config.settings import AppSettings


def test_load_merges_yaml_with_env_overrides(monkeypatch, tmp_path: Path) -> None:
    yaml_path = tmp_path / "settings.yaml"
    yaml_path.write_text(
        """coze:
  access_token: yaml-coze
  base_url: https://yaml.coze
  timeout_seconds: 10
dify:
  api_key: yaml-dify
  base_url: https://yaml.dify
n8n:
  base_url: https://yaml.n8n/api
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("TESTCODE_COZE_ACCESS_TOKEN", "env-coze")
    monkeypatch.setenv("TESTCODE_N8N_TIMEOUT_SECONDS", "45")

    settings = AppSettings.load(yaml_path)

    assert settings.coze.access_token == "env-coze"
    assert settings.coze.base_url == "https://yaml.coze"
    assert settings.coze.timeout_seconds == 10.0
    assert settings.dify.api_key == "yaml-dify"
    assert settings.dify.base_url == "https://yaml.dify"
    assert settings.n8n.base_url == "https://yaml.n8n/api"
    assert settings.n8n.timeout_seconds == 45.0


def test_load_without_yaml_uses_env_and_defaults(monkeypatch) -> None:
    monkeypatch.setenv("TESTCODE_DIFY_API_KEY", "env-key")

    settings = AppSettings.load(path=None)

    assert settings.dify.api_key == "env-key"
    assert settings.coze.base_url == "https://api.coze.com"
