from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from testcode.cli import app


runner = CliRunner()


def test_health_command_with_settings(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        """coze:
  access_token: token
dify:
  api_key: key
n8n:
  base_url: https://n8n.example.com/api
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["health", "--settings", str(settings_path)])

    assert result.exit_code == 0
    assert "status" in result.stdout
