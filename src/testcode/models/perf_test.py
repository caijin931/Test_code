"""Pydantic models for performance / load testing."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class LoadPattern(str, Enum):
    """Load generation patterns for performance tests."""

    CONSTANT = "constant"
    RAMP_UP = "ramp_up"
    SPIKE = "spike"
    SOAK = "soak"


class PerformanceProfile(BaseModel):
    """Configuration for a performance test run."""

    request_id: str
    profile_name: str
    target_url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    load_pattern: LoadPattern = LoadPattern.CONSTANT
    concurrency: int = Field(default=10, ge=1, le=10000)
    duration_seconds: int = Field(default=60, ge=1, le=3600)
    ramp_up_seconds: int = Field(default=0, ge=0)
    think_time_ms: float = Field(default=0.0, ge=0.0)
    warmup_seconds: int = Field(default=0, ge=0)
    env: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator("ramp_up_seconds")
    @classmethod
    def ramp_up_must_fit_duration(cls, v: int, info: Any) -> int:
        """Ensure ramp_up_seconds does not exceed duration_seconds."""
        duration = info.data.get("duration_seconds")
        if duration is not None and v > duration:
            raise ValueError(f"ramp_up_seconds ({v}) must not exceed duration_seconds ({duration})")
        return v


class PerfMetricSnapshot(BaseModel):
    """A snapshot of performance metrics at a point in time."""

    timestamp_seconds: float
    requests_completed: int = 0
    requests_in_flight: int = 0
    errors_count: int = 0
    response_time_min_ms: float = 0.0
    response_time_max_ms: float = 0.0
    response_time_avg_ms: float = 0.0
    response_time_p50_ms: float = 0.0
    response_time_p95_ms: float = 0.0
    response_time_p99_ms: float = 0.0
    throughput_rps: float = 0.0


class PerfTestResult(BaseModel):
    """Aggregated results of a full performance test run."""

    request_id: str
    profile: PerformanceProfile
    total_requests: int = 0
    total_errors: int = 0
    error_rate: float = 0.0
    duration_seconds: float = 0.0
    snapshots: list[PerfMetricSnapshot] = Field(default_factory=list)
    aggregate: PerfMetricSnapshot | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class PerfTestReport(BaseModel):
    """Human-readable performance analysis report."""

    request_id: str
    summary: str
    risk_level: str = "medium"
    highlights: list[str] = Field(default_factory=list)
    bottlenecks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
