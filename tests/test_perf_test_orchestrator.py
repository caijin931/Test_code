"""Unit tests for PerfTestOrchestrator."""

from __future__ import annotations

from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

import httpx
import pytest

from testcode.adapters.coze import CozeClient
from testcode.adapters.dify import DifyClient
from testcode.adapters.n8n import N8nClient
from testcode.models.perf_test import LoadPattern, PerfMetricSnapshot, PerfTestResult, PerformanceProfile
from testcode.perf_test_orchestrator import PerfTestOrchestrator
from testcode.providers.registry import ProviderRegistry


class StubTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def _make_registry() -> ProviderRegistry:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    http = httpx.Client(transport=StubTransport(handler), base_url="https://test.example.com")
    return ProviderRegistry(
        coze=CozeClient(access_token="token", client=http),
        dify=DifyClient(api_key="key", client=http),
        n8n=N8nClient(base_url="https://n8n.example.com/api", client=http),
    )


# ---------------------------------------------------------------------------
# local test server helper
# ---------------------------------------------------------------------------


class _TestHandler(BaseHTTPRequestHandler):
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


def _start_test_server() -> tuple[HTTPServer, str]:
    """Start a local HTTP server on a free port. Returns (server, url)."""
    server = HTTPServer(("127.0.0.1", 0), _TestHandler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/health"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, url


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_perf_test_basic_execution() -> None:
    """Run a short (3-second) test against a local stub server."""
    server, target_url = _start_test_server()
    try:
        registry = _make_registry()
        profile = PerformanceProfile(
            request_id="req-1",
            profile_name="Basic Test",
            target_url=target_url,
            concurrency=2,
            duration_seconds=3,
        )

        orch = PerfTestOrchestrator(registry=registry)
        result = orch.execute_perf_test(profile)

        assert result["profile"] == profile
        assert result["result"].total_requests > 0
        assert result["report"].summary != ""
    finally:
        server.shutdown()


def test_perf_test_empty_target_raises() -> None:
    """Missing target_url should raise ValueError."""
    registry = _make_registry()
    profile = PerformanceProfile(request_id="req-2", profile_name="Bad", target_url="")

    orch = PerfTestOrchestrator(registry=registry)
    with pytest.raises(ValueError, match="must not be empty"):
        orch.execute_perf_test(profile)


def test_perf_test_metric_computation() -> None:
    """Percentile computation produces correct values."""
    orch = PerfTestOrchestrator(registry=_make_registry())

    data = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    p50 = orch._percentile(data, 50)
    assert 50.0 <= p50 <= 60.0  # median of 10 values
    assert orch._percentile(data, 95) > 80.0
    assert orch._percentile([], 50) == 0.0
    assert orch._percentile([42.0], 50) == 42.0


def test_perf_test_aggregate_computation() -> None:
    """Aggregate is computed correctly from multiple snapshots."""
    orch = PerfTestOrchestrator(registry=_make_registry())

    snapshots = [
        PerfMetricSnapshot(
            timestamp_seconds=1.0,
            requests_completed=10,
            errors_count=0,
            response_time_min_ms=50.0,
            response_time_max_ms=200.0,
            response_time_avg_ms=120.0,
            response_time_p50_ms=110.0,
            response_time_p95_ms=180.0,
            response_time_p99_ms=195.0,
            throughput_rps=10.0,
        ),
        PerfMetricSnapshot(
            timestamp_seconds=2.0,
            requests_completed=25,
            errors_count=1,
            response_time_min_ms=40.0,
            response_time_max_ms=300.0,
            response_time_avg_ms=140.0,
            response_time_p50_ms=130.0,
            response_time_p95_ms=250.0,
            response_time_p99_ms=290.0,
            throughput_rps=15.0,
        ),
    ]

    agg = orch._compute_aggregate(snapshots)
    assert agg is not None
    assert agg.requests_completed == 25
    assert agg.errors_count == 1
    assert agg.response_time_min_ms == 40.0
    assert agg.response_time_max_ms == 300.0
    assert agg.throughput_rps == 15.0  # max


def test_perf_test_ramp_up_pattern() -> None:
    """Ramp-up profile executes without error."""
    server, target_url = _start_test_server()
    try:
        registry = _make_registry()
        profile = PerformanceProfile(
            request_id="req-ramp",
            profile_name="Ramp Up Test",
            target_url=target_url,
            load_pattern=LoadPattern.RAMP_UP,
            concurrency=4,
            duration_seconds=3,
            ramp_up_seconds=2,
        )

        orch = PerfTestOrchestrator(registry=registry)
        result = orch.execute_perf_test(profile)

        assert result["result"].total_requests > 0
    finally:
        server.shutdown()


def test_perf_test_report_bottlenecks() -> None:
    """Report includes bottlenecks when performance is poor."""
    registry = _make_registry()
    profile = PerformanceProfile(
        request_id="req-3",
        profile_name="Slow Test",
        target_url="https://test.example.com/slow",
    )
    aggregate = PerfMetricSnapshot(
        timestamp_seconds=10.0,
        requests_completed=100,
        errors_count=10,
        response_time_min_ms=100.0,
        response_time_max_ms=5000.0,
        response_time_avg_ms=800.0,
        response_time_p50_ms=600.0,
        response_time_p95_ms=1200.0,
        response_time_p99_ms=3000.0,
        throughput_rps=10.0,
    )
    perf_result = PerfTestResult(
        request_id="req-3",
        profile=profile,
        total_requests=100,
        total_errors=10,
        error_rate=0.10,
        duration_seconds=10.0,
        aggregate=aggregate,
    )

    orch = PerfTestOrchestrator(registry=registry)
    report = orch._analyze_with_dify(perf_result)

    assert report.risk_level == "P0"
    assert len(report.bottlenecks) > 0
    assert len(report.recommendations) > 0


def test_perf_test_no_aggregate_report() -> None:
    """Report when no aggregate data is available."""
    registry = _make_registry()
    profile = PerformanceProfile(
        request_id="req-4",
        profile_name="Empty",
        target_url="https://test.example.com/none",
    )
    perf_result = PerfTestResult(request_id="req-4", profile=profile)

    orch = PerfTestOrchestrator(registry=registry)
    report = orch._analyze_with_dify(perf_result)

    assert report.risk_level == "P0"
    assert "No performance data collected" in report.summary
