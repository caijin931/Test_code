"""CLI tests for the perf-test command."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
import threading

from typer.testing import CliRunner

from testcode.cli import app

runner = CliRunner()


class _PerfTestHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for perf test target."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_POST(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, format, *args):  # noqa: A002
        pass  # suppress logs


def _start_server() -> tuple[HTTPServer, str]:
    """Start a local HTTP server on a free port. Returns (server, target_url)."""
    server = HTTPServer(("127.0.0.1", 0), _PerfTestHandler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/health"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, url


def _write_settings(settings_path: Path) -> None:
    settings_path.write_text(
        "coze:\n  access_token: tok\n  base_url: https://api.coze.com\n"
        "dify:\n  api_key: key\n  base_url: https://api.dify.ai\n"
        "n8n:\n  base_url: https://n8n.example.com/api\n",
        encoding="utf-8",
    )


def test_perf_test_command_with_output(tmp_path: Path) -> None:
    """perf-test with valid args writes result to output file using local server."""
    server, target_url = _start_server()
    try:
        settings_path = tmp_path / "settings.yaml"
        _write_settings(settings_path)

        output_file = tmp_path / "perf-output.json"

        result = runner.invoke(
            app,
            [
                "perf-test",
                "--settings", str(settings_path),
                "--target-url", target_url,
                "--duration", "3",
                "--concurrency", "2",
                "--output", str(output_file),
            ],
        )

        assert result.exit_code == 0
        assert output_file.exists()
        data = json.loads(output_file.read_text(encoding="utf-8"))
        assert "result" in data
        assert "report" in data
    finally:
        server.shutdown()


def test_perf_test_command_invalid_pattern(tmp_path: Path) -> None:
    """Invalid load pattern should produce error."""
    settings_path = tmp_path / "settings.yaml"
    _write_settings(settings_path)

    result = runner.invoke(
        app,
        [
            "perf-test",
            "--settings", str(settings_path),
            "--target-url", "https://httpbin.org/get",
            "--load-pattern", "invalid_pattern",
            "--duration", "3",
        ],
    )

    assert result.exit_code != 0


def test_perf_test_command_stdout_contains_results(tmp_path: Path) -> None:
    """perf-test stdout contains expected keys using local server."""
    server, target_url = _start_server()
    try:
        settings_path = tmp_path / "settings.yaml"
        _write_settings(settings_path)

        result = runner.invoke(
            app,
            [
                "perf-test",
                "--settings", str(settings_path),
                "--target-url", target_url,
                "--duration", "3",
                "--concurrency", "2",
            ],
        )

        assert result.exit_code == 0
        assert '"result"' in result.stdout
        assert '"report"' in result.stdout
    finally:
        server.shutdown()
