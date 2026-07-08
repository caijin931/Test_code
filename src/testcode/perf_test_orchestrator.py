"""Orchestrator for performance / load testing.

Generates concurrent HTTP traffic against a target URL, collects per-second
metric snapshots, computes aggregates, and produces analysis reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import asyncio
import logging
import statistics
import time

import httpx

from testcode.models.perf_test import (
    LoadPattern,
    PerfMetricSnapshot,
    PerfTestReport,
    PerfTestResult,
    PerformanceProfile,
)
from testcode.providers.registry import ProviderRegistry


@dataclass(slots=True)
class PerfTestOrchestrator:
    """Orchestrates performance / load test execution and analysis."""

    registry: ProviderRegistry
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("testcode.perf_test_orchestrator")
    )

    # ------------------------------------------------------------------
    # public pipeline
    # ------------------------------------------------------------------

    def execute_perf_test(
        self,
        profile: PerformanceProfile,
        *,
        use_coze_analysis: bool = False,
        coze_bot_id: str | None = None,
        coze_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute the performance test pipeline.

        Returns a dict with keys: ``profile``, ``result``, ``report``.
        """
        if not profile.target_url.strip():
            raise ValueError("PerformanceProfile.target_url must not be empty")

        # --- optional Coze pre-analysis ---
        if use_coze_analysis and coze_bot_id and coze_user_id:
            self._analyze_with_coze(profile, coze_bot_id, coze_user_id)

        # --- warmup ---
        if profile.warmup_seconds > 0:
            self.logger.info(
                "Warmup phase starting", extra={"duration": profile.warmup_seconds}
            )
            asyncio.run(self._run_warmup(profile))

        # --- main load test ---
        self.logger.info(
            "Load test starting",
            extra={"target": profile.target_url, "concurrency": profile.concurrency},
        )
        start_time = time.monotonic()
        completed, errors, snapshots = asyncio.run(self._run_load(profile))
        elapsed = time.monotonic() - start_time

        # --- build result ---
        total_requests = len(completed)
        total_errors = len(errors)
        aggregate = self._compute_aggregate(snapshots) if snapshots else None

        result = PerfTestResult(
            request_id=profile.request_id,
            profile=profile,
            total_requests=total_requests,
            total_errors=total_errors,
            error_rate=round(total_errors / total_requests, 4) if total_requests > 0 else 0.0,
            duration_seconds=round(elapsed, 2),
            snapshots=snapshots,
            aggregate=aggregate,
        )

        # --- generate report via Dify ---
        report = self._analyze_with_dify(result)

        self.logger.info(
            "Load test complete",
            extra={
                "request_id": profile.request_id,
                "total_requests": total_requests,
                "error_rate": result.error_rate,
            },
        )

        return {"profile": profile, "result": result, "report": report}

    # ------------------------------------------------------------------
    # async load generator
    # ------------------------------------------------------------------

    async def _run_load(
        self, profile: PerformanceProfile
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[PerfMetricSnapshot]]:
        """Run the load test with periodic metric collection."""
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        snapshots: list[PerfMetricSnapshot] = []

        semaphore = asyncio.Semaphore(profile.concurrency)
        start = time.monotonic()
        end_at = start + profile.duration_seconds
        request_count = 0
        response_times: list[float] = []

        # Allow injecting an async client for testing
        injected_client: httpx.AsyncClient | None = getattr(self, "_async_client", None)
        own_client = injected_client is None
        shared_client = injected_client or httpx.AsyncClient(timeout=30.0)

        try:
            async def worker() -> None:
                nonlocal request_count
                while time.monotonic() < end_at:
                    if profile.think_time_ms > 0:
                        await asyncio.sleep(profile.think_time_ms / 1000)

                    async with semaphore:
                        req_start = time.monotonic()
                        try:
                            body_json = profile.body is not None and isinstance(profile.body, (dict, list))
                            body_raw = profile.body is not None and isinstance(profile.body, (str, bytes))
                            resp = await shared_client.request(
                                method=profile.method,
                                url=profile.target_url,
                                headers=profile.headers or None,
                                json=profile.body if body_json else None,
                                content=profile.body if body_raw else None,
                            )
                            rt = (time.monotonic() - req_start) * 1000
                            request_count += 1
                            response_times.append(rt)
                            results.append(
                                {
                                    "status_code": resp.status_code,
                                    "response_time_ms": rt,
                                    "timestamp": time.monotonic(),
                                }
                            )
                        except Exception as exc:
                            rt = (time.monotonic() - req_start) * 1000
                            request_count += 1
                            response_times.append(rt)
                            errors.append(
                                {
                                    "error": str(exc),
                                    "response_time_ms": rt,
                                    "timestamp": time.monotonic(),
                                }
                            )

            # Apply ramp-up: gradually increase concurrency
            if profile.load_pattern == LoadPattern.RAMP_UP and profile.ramp_up_seconds > 0:
                current_concurrency = 1
                ramp_end = start + profile.ramp_up_seconds
                workers: list[asyncio.Task[None]] = []
                while time.monotonic() < ramp_end and current_concurrency <= profile.concurrency:
                    workers.append(asyncio.create_task(worker()))
                    current_concurrency += 1
                    await asyncio.sleep(profile.ramp_up_seconds / profile.concurrency)
                # Continue with remaining workers
                while len(workers) < profile.concurrency:
                    workers.append(asyncio.create_task(worker()))
            else:
                workers = [asyncio.create_task(worker()) for _ in range(profile.concurrency)]

            # Periodic metric collection
            collector_stop = asyncio.Event()

            async def collect_metrics() -> None:
                prev = 0
                while not collector_stop.is_set():
                    await asyncio.sleep(1.0)
                    elapsed = time.monotonic() - start
                    snapshot = self._build_snapshot(
                        elapsed, request_count, response_times,
                        profile.concurrency, semaphore, errors, prev,
                    )
                    prev = request_count
                    snapshots.append(snapshot)

            collector_task = asyncio.create_task(collect_metrics())

            # Wait until duration expires
            remaining = end_at - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)

            # Stop collector
            collector_stop.set()
            await collector_task

            # Cancel running workers
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            return results, errors, snapshots
        finally:
            if own_client:
                await shared_client.aclose()

    async def _run_warmup(self, profile: PerformanceProfile) -> None:
        """Send low-concurrency warmup requests before the main test."""
        end_at = time.monotonic() + profile.warmup_seconds
        async with httpx.AsyncClient(timeout=30.0) as client:
            while time.monotonic() < end_at:
                try:
                    await client.request(
                        method=profile.method,
                        url=profile.target_url,
                        headers=profile.headers or None,
                    )
                except Exception:
                    pass  # Warmup errors are expected
                await asyncio.sleep(0.5)

    # ------------------------------------------------------------------
    # metrics
    # ------------------------------------------------------------------

    def _build_snapshot(
        self,
        elapsed: float,
        request_count: int,
        response_times: list[float],
        concurrency: int,
        semaphore: asyncio.Semaphore,
        errors: list[dict[str, Any]],
        prev_count: int = 0,
    ) -> PerfMetricSnapshot:
        """Build a PerfMetricSnapshot from current state."""
        times_in_window = list(response_times)  # snapshot of all collected so far

        # requests_in_flight = total concurrency - available permits
        in_flight = max(0, concurrency - (semaphore._value if hasattr(semaphore, '_value') else 0))

        # per-second throughput (delta since last snapshot)
        delta_count = max(0, request_count - prev_count)

        return PerfMetricSnapshot(
            timestamp_seconds=round(elapsed, 2),
            requests_completed=request_count,
            requests_in_flight=in_flight,
            errors_count=len(errors),
            response_time_min_ms=round(min(times_in_window), 2) if times_in_window else 0.0,
            response_time_max_ms=round(max(times_in_window), 2) if times_in_window else 0.0,
            response_time_avg_ms=round(statistics.mean(times_in_window), 2) if times_in_window else 0.0,
            response_time_p50_ms=self._percentile(times_in_window, 50),
            response_time_p95_ms=self._percentile(times_in_window, 95),
            response_time_p99_ms=self._percentile(times_in_window, 99),
            throughput_rps=round(delta_count, 2),
        )

    def _compute_aggregate(
        self, snapshots: list[PerfMetricSnapshot]
    ) -> PerfMetricSnapshot | None:
        """Compute aggregate metrics from all snapshots."""
        if not snapshots:
            return None
        last = snapshots[-1]
        all_times = [s.response_time_avg_ms for s in snapshots if s.response_time_avg_ms > 0]

        return PerfMetricSnapshot(
            timestamp_seconds=last.timestamp_seconds,
            requests_completed=last.requests_completed,
            requests_in_flight=0,
            errors_count=last.errors_count,
            response_time_min_ms=min(s.response_time_min_ms for s in snapshots if s.response_time_min_ms > 0) if any(s.response_time_min_ms > 0 for s in snapshots) else 0.0,
            response_time_max_ms=max(s.response_time_max_ms for s in snapshots),
            response_time_avg_ms=round(statistics.mean(all_times), 2) if all_times else 0.0,
            response_time_p50_ms=self._percentile(all_times, 50),
            response_time_p95_ms=self._percentile(all_times, 95),
            response_time_p99_ms=self._percentile(all_times, 99),
            throughput_rps=max(s.throughput_rps for s in snapshots) if snapshots else 0.0,
        )

    @staticmethod
    def _percentile(data: list[float], pct: float) -> float:
        """Compute the pct-th percentile from a list of floats."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        n = len(sorted_data)
        if n == 0:
            return 0.0
        k = (pct / 100) * (n - 1)
        f = int(k)
        c = k - f
        if f + 1 < n:
            return round(sorted_data[f] + c * (sorted_data[f + 1] - sorted_data[f]), 2)
        return round(sorted_data[f], 2)

    # ------------------------------------------------------------------
    # Dify analysis
    # ------------------------------------------------------------------

    def _analyze_with_dify(self, result: PerfTestResult) -> PerfTestReport:
        """Generate a performance analysis report, optionally via Dify."""
        aggregate = result.aggregate

        # Build summary from aggregate data
        if aggregate is None:
            return PerfTestReport(
                request_id=result.request_id,
                summary="No performance data collected.",
                risk_level="P0",
                highlights=[],
                bottlenecks=["No data available"],
                recommendations=["Re-run the test with a reachable target URL"],
            )

        p95 = aggregate.response_time_p95_ms
        p99 = aggregate.response_time_p99_ms
        avg = aggregate.response_time_avg_ms
        error_rate = result.error_rate

        # Determine risk level
        risk_level = "P3"
        bottlenecks: list[str] = []
        recommendations: list[str] = []

        if error_rate > 0.05:
            risk_level = "P0"
            bottlenecks.append(f"Error rate {error_rate:.1%} exceeds 5% threshold")
            recommendations.append("Investigate error responses and add retry logic")
        elif error_rate > 0.01:
            risk_level = "P2"
            bottlenecks.append(f"Error rate {error_rate:.1%} exceeds 1% threshold")

        if p95 > 1000:
            risk_level = "P0"
            bottlenecks.append(f"P95 response time ({p95:.0f}ms) exceeds 1000ms")
            recommendations.append("Optimize slow endpoints and add caching")
        elif p95 > 500:
            if risk_level == "P3":
                risk_level = "P2"
            bottlenecks.append(f"P95 response time ({p95:.0f}ms) exceeds 500ms")

        if p99 > 2000:
            bottlenecks.append(f"P99 response time ({p99:.0f}ms) exceeds 2000ms — tail latency issue")
            recommendations.append("Investigate tail latency: connection pooling, GC pauses")

        highlights: list[str] = [
            f"Total requests: {result.total_requests}",
            f"Avg response time: {avg:.0f}ms",
            f"P95: {p95:.0f}ms, P99: {p99:.0f}ms",
            f"Error rate: {error_rate:.2%}",
        ]

        if not bottlenecks:
            highlights.append("No bottlenecks detected")

        # Try Dify for enhanced analysis
        summary = f"Performance test completed. {result.total_requests} requests sent over {result.duration_seconds:.0f}s."
        try:
            dify = self.registry.get("dify")
            dify_result = dify.chat(
                query=f"Analyze performance test: {result.total_requests} requests, avg {avg:.0f}ms, p95 {p95:.0f}ms, p99 {p99:.0f}ms, error rate {error_rate:.2%}",
                user="perf-orchestrator",
                inputs={"metrics": highlights},
            )
            if dify_result.content:
                summary = dify_result.content
        except Exception as exc:
            self.logger.warning("Dify analysis unavailable, using heuristics", extra={"error": str(exc)})

        return PerfTestReport(
            request_id=result.request_id,
            summary=summary,
            risk_level=risk_level,
            highlights=highlights,
            bottlenecks=bottlenecks,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Coze pre-analysis
    # ------------------------------------------------------------------

    def _analyze_with_coze(
        self, profile: PerformanceProfile, bot_id: str, user_id: str
    ) -> None:
        """Use Coze for pre-test analysis suggestions."""
        try:
            coze = self.registry.get("coze")
            coze.chat(
                bot_id=bot_id,
                user_id=user_id,
                query=f"Analyze performance test profile: target={profile.target_url}, "
                f"pattern={profile.load_pattern.value}, concurrency={profile.concurrency}, "
                f"duration={profile.duration_seconds}s. Suggest additional metrics or test scenarios.",
            )
        except Exception as exc:
            self.logger.warning("Coze analysis skipped", extra={"error": str(exc)})
