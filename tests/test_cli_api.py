"""CLI tests for the api-test command."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
import threading

from typer.testing import CliRunner

from testcode.cli import app

runner = CliRunner()


class _ApiTestHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for CLI api-test target."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def do_POST(self) -> None:
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"created": true}')

    def log_message(self, format, *args):  # noqa: A002
        pass  # suppress logs


def _start_server() -> tuple[HTTPServer, str]:
    """Start a local HTTP server on a free port. Returns (server, base_url)."""
    server = HTTPServer(("127.0.0.1", 0), _ApiTestHandler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}"
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


def test_api_test_command_with_output(tmp_path: Path) -> None:
    """api-test with valid settings writes result to output file using local server."""
    server, base_url = _start_server()
    try:
        settings_path = tmp_path / "settings.yaml"
        _write_settings(settings_path)

        endpoints_json = tmp_path / "endpoints.json"
        endpoints_json.write_text(
            json.dumps(
                [
                    {"endpoint_id": "ep-1", "name": "Health", "method": "GET", "url": "/health"},
                    {"endpoint_id": "ep-2", "name": "Users", "method": "GET", "url": "/users"},
                ]
            ),
            encoding="utf-8",
        )

        output_file = tmp_path / "output.json"

        result = runner.invoke(
            app,
            [
                "api-test",
                "--settings", str(settings_path),
                "--suite-name", "CLI Suite",
                "--base-url", base_url,
                "--endpoints-file", str(endpoints_json),
                "--output", str(output_file),
            ],
        )

        assert result.exit_code == 0
        assert output_file.exists()
        data = json.loads(output_file.read_text(encoding="utf-8"))
        assert "report" in data
        assert "results" in data
    finally:
        server.shutdown()


def test_api_test_command_missing_endpoints_file(tmp_path: Path) -> None:
    """Missing endpoints file should produce error exit code."""
    settings_path = tmp_path / "settings.yaml"
    _write_settings(settings_path)

    result = runner.invoke(
        app,
        [
            "api-test",
            "--settings", str(settings_path),
            "--suite-name", "Bad Suite",
            "--base-url", "https://httpbin.org",
            "--endpoints-file", str(tmp_path / "nonexistent.json"),
        ],
    )

    assert result.exit_code != 0


def test_api_test_command_stdout_contains_results(tmp_path: Path) -> None:
    """api-test stdout contains expected keys using local server."""
    server, base_url = _start_server()
    try:
        settings_path = tmp_path / "settings.yaml"
        _write_settings(settings_path)

        endpoints_json = tmp_path / "endpoints.json"
        endpoints_json.write_text(
            json.dumps(
                [
                    {"endpoint_id": "ep-1", "name": "Health", "method": "GET", "url": "/health"},
                ]
            ),
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            [
                "api-test",
                "--settings", str(settings_path),
                "--suite-name", "Output Suite",
                "--base-url", base_url,
                "--endpoints-file", str(endpoints_json),
            ],
        )

        assert result.exit_code == 0
        assert '"report"' in result.stdout
        assert '"results"' in result.stdout
    finally:
        server.shutdown()
