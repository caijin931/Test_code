from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from testcode.cli import app


runner = CliRunner()


def test_run_test_flow_accepts_requirement_and_writes_output(tmp_path: Path) -> None:
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
    requirement_file = tmp_path / "req.txt"
    requirement_file.write_text("测试登录功能", encoding="utf-8")
    output_file = tmp_path / "result.json"

    result = runner.invoke(
        app,
        [
            "run-test-flow",
            "--settings",
            str(settings_path),
            "--requirement-file",
            str(requirement_file),
            "--n8n-webhook-url",
            "https://example.com/webhook",
            "--output",
            str(output_file),
        ],
    )

    assert result.exit_code == 0
    assert output_file.exists()
    assert "测试登录功能" in output_file.read_text(encoding="utf-8")
