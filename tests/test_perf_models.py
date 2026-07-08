"""Unit tests for performance testing Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from testcode.models import (
    LoadPattern,
    PerfMetricSnapshot,
    PerfTestReport,
    PerfTestResult,
    PerformanceProfile,
)


def test_performance_profile_validation() -> None:
    """A PerformanceProfile requires request_id, profile_name, target_url."""
    profile = PerformanceProfile(
        request_id="req-1",
        profile_name="Login Load Test",
        target_url="https://example.com/api/login",
    )
    assert profile.method == "GET"
    assert profile.load_pattern == LoadPattern.CONSTANT
    assert profile.concurrency == 10
    assert profile.duration_seconds == 60


def test_performance_profile_all_patterns() -> None:
    """All LoadPattern values are accepted."""
    for pattern in LoadPattern:
        profile = PerformanceProfile(
            request_id="req-1",
            profile_name=f"Test {pattern.value}",
            target_url="https://example.com/api/test",
            load_pattern=pattern,
        )
        assert profile.load_pattern == pattern


def test_performance_profile_invalid_pattern_raises() -> None:
    """Invalid load pattern should raise ValidationError."""
    with pytest.raises(ValidationError):
        PerformanceProfile(
            request_id="req-1",
            profile_name="Bad Pattern",
            target_url="https://example.com/test",
            load_pattern="invalid",  # type: ignore[arg-type]
        )


def test_performance_profile_missing_target_url() -> None:
    """Missing target_url should raise ValidationError."""
    with pytest.raises(ValidationError):
        PerformanceProfile(
            request_id="req-1",
            profile_name="Missing URL",
            # target_url is required, intentionally omitted
        )  # type: ignore[call-arg]


def test_perf_metric_snapshot_defaults() -> None:
    """PerfMetricSnapshot defaults are sensible."""
    snapshot = PerfMetricSnapshot(timestamp_seconds=1.0)
    assert snapshot.requests_completed == 0
    assert snapshot.requests_in_flight == 0
    assert snapshot.errors_count == 0
    assert snapshot.response_time_min_ms == 0.0
    assert snapshot.response_time_max_ms == 0.0
    assert snapshot.response_time_avg_ms == 0.0
    assert snapshot.response_time_p50_ms == 0.0
    assert snapshot.response_time_p95_ms == 0.0
    assert snapshot.response_time_p99_ms == 0.0
    assert snapshot.throughput_rps == 0.0


def test_perf_metric_snapshot_full() -> None:
    """PerfMetricSnapshot accepts full data."""
    snapshot = PerfMetricSnapshot(
        timestamp_seconds=5.0,
        requests_completed=100,
        requests_in_flight=8,
        errors_count=2,
        response_time_min_ms=12.0,
        response_time_max_ms=450.0,
        response_time_avg_ms=85.3,
        response_time_p50_ms=72.0,
        response_time_p95_ms=200.0,
        response_time_p99_ms=380.0,
        throughput_rps=20.0,
    )
    assert snapshot.requests_completed == 100
    assert snapshot.throughput_rps == 20.0


def test_perf_test_result_defaults() -> None:
    """PerfTestResult has sensible defaults."""
    profile = PerformanceProfile(
        request_id="req-1",
        profile_name="Test",
        target_url="https://example.com/test",
    )
    result = PerfTestResult(request_id="req-1", profile=profile)
    assert result.total_requests == 0
    assert result.total_errors == 0
    assert result.error_rate == 0.0
    assert result.duration_seconds == 0.0
    assert result.snapshots == []
    assert result.aggregate is None


def test_perf_test_result_with_aggregate() -> None:
    """PerfTestResult holds aggregate snapshot."""
    profile = PerformanceProfile(
        request_id="req-2",
        profile_name="Load Test",
        target_url="https://example.com/api",
        concurrency=50,
        duration_seconds=30,
    )
    aggregate = PerfMetricSnapshot(
        timestamp_seconds=30.0,
        requests_completed=1500,
        requests_in_flight=0,
        errors_count=5,
        response_time_min_ms=10.0,
        response_time_max_ms=500.0,
        response_time_avg_ms=95.0,
        response_time_p50_ms=80.0,
        response_time_p95_ms=250.0,
        response_time_p99_ms=420.0,
        throughput_rps=50.0,
    )
    result = PerfTestResult(
        request_id="req-2",
        profile=profile,
        total_requests=1500,
        total_errors=5,
        error_rate=0.0033,
        duration_seconds=30.0,
        aggregate=aggregate,
    )
    assert result.aggregate is not None
    assert result.aggregate.throughput_rps == 50.0
    assert result.error_rate == pytest.approx(0.0033, abs=0.01)


def test_perf_test_report_fields() -> None:
    """PerfTestReport holds required and optional fields."""
    report = PerfTestReport(
        request_id="req-1",
        summary="Performance test completed with 95th percentile at 250ms.",
        risk_level="P3",
        highlights=["All requests succeeded", "p95 < 300ms"],
        bottlenecks=[],
        recommendations=["Consider CDN for static assets"],
    )
    assert report.summary != ""
    assert report.risk_level == "P3"
    assert len(report.highlights) == 2
    assert len(report.recommendations) == 1


def test_perf_test_report_with_bottlenecks() -> None:
    """PerfTestReport with bottleneck analysis."""
    report = PerfTestReport(
        request_id="req-3",
        summary="Significant performance degradation detected.",
        risk_level="P0",
        highlights=["Throughput dropped after 100 concurrent users"],
        bottlenecks=["Database connection pool exhausted at 100 connections"],
        recommendations=["Increase pool size to 200", "Add connection pooling"],
    )
    assert len(report.bottlenecks) == 1
    assert len(report.recommendations) == 2
    assert report.risk_level == "P0"
