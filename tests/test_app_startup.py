from __future__ import annotations

from pathlib import Path

from testcode.app import build_orchestrator


def test_build_orchestrator_from_settings(tmp_path: Path, monkeypatch) -> None:
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

    orchestrator = build_orchestrator(yaml_path)

    assert orchestrator.registry is not None
    assert orchestrator.registry.coze.access_token == "token"
    assert orchestrator.registry.dify.api_key == "key"
    assert orchestrator.registry.n8n.base_url == "https://n8n.example.com/api"
