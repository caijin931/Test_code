from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from testcode.cli import app


runner = CliRunner()


def test_cache_health_command_reports_cache_status(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        """coze:
  access_token: token
dify:
  api_key: key
  cache_enabled: false
n8n:
  base_url: https://n8n.example.com/api
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["cache-health", "--settings", str(settings_path)])

    assert result.exit_code == 0
    assert "dify" in result.stdout.lower()
