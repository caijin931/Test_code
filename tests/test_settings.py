from __future__ import annotations

from pathlib import Path

from testcode.config.settings import AppSettings


def test_app_settings_from_mapping_applies_defaults() -> None:
    settings = AppSettings.from_mapping({"coze": {"access_token": "token"}})

    assert settings.coze.access_token == "token"
    assert settings.coze.base_url == "https://api.coze.com"
    assert settings.dify.base_url == "https://api.dify.ai"
    assert settings.n8n.base_url == ""


def test_app_settings_from_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "settings.yaml"
    yaml_path.write_text(
        """coze:
  access_token: token
dify:
  api_key: key
n8n:
  base_url: https://n8n.example.com/api
""",
        encoding="utf-8",
    )

    settings = AppSettings.from_yaml(yaml_path)

    assert settings.coze.access_token == "token"
    assert settings.dify.api_key == "key"
    assert settings.n8n.base_url == "https://n8n.example.com/api"
