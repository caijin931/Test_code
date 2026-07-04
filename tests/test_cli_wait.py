from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from testcode.cli import app


runner = CliRunner()


def test_run_command_supports_wait(tmp_path: Path) -> None:
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

    result = runner.invoke(
        app,
        [
            "run",
            "--settings",
            str(settings_path),
            "--coze-bot-id",
            "bot-1",
            "--coze-user-id",
            "user-1",
            "--coze-query",
            "hello",
            "--dify-user",
            "user-2",
            "--n8n-webhook-url",
            "https://example.com/webhook",
            "--wait",
        ],
    )

    assert result.exit_code == 0
    assert "n8n" in result.stdout
