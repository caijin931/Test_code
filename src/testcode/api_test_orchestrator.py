"""Orchestrator for API / interface testing.

Executes HTTP requests against configured endpoints, evaluates assertions,
and produces structured test reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import json
import logging
import re
import time

import httpx

from testcode.models.api_test import (
    ApiEndpoint,
    ApiExecutionResult,
    ApiResponseAssertion,
    ApiTestReport,
    ApiTestSuite,
)
from testcode.providers.registry import ProviderRegistry


def _resolve_jsonpath(data: Any, path: str) -> Any:
    """Resolve a simple dot-notation or JSONPath expression against data.

    Supports:
      - "status_code" -> literal key lookup in dict
      - "$.data.id" -> nested dict traversal
      - "$.items[0].name" -> list index access
      - "$.headers.content-type" -> nested access

    Falls back to returning None when a key/index is missing.
    """
    if path == "$":
        return data

    if path == "status_code":
        return data.get("status_code") if isinstance(data, dict) else None

    # Strip "$." prefix if present
    expr = path[2:] if path.startswith("$.") else path
    if not expr:
        return data

    current: Any = data
    for segment in expr.split("."):
        if current is None:
            return None
        # Handle array index: "items[0]"
        match = re.match(r"^(\w+)\[(\d+)\]$", segment)
        if match:
            key, idx = match.groups()
            current = current.get(key) if isinstance(current, dict) else None
            if isinstance(current, list) and int(idx) < len(current):
                current = current[int(idx)]
            else:
                return None
            continue
        # Handle dict access
        if isinstance(current, dict):
            current = current.get(segment)
        else:
            return None
    return current


def _evaluate_operator(actual: Any, operator: str, expected: Any) -> bool:
    """Evaluate a comparison operator against actual and expected values."""
    if operator == "equals":
        return actual == expected
    if operator == "contains":
        if isinstance(actual, str) and isinstance(expected, str):
            return expected in actual
        if isinstance(actual, (list, tuple)):
            return expected in actual
        return False
    if operator == "matches_regex":
        try:
            return bool(re.search(str(expected), str(actual)))
        except re.error:
            return False
    if operator == "less_than":
        try:
            return float(actual) < float(expected)
        except (TypeError, ValueError):
            return False
    if operator == "greater_than":
        try:
            return float(actual) > float(expected)
        except (TypeError, ValueError):
            return False
    return False


@dataclass(slots=True)
class ApiTestOrchestrator:
    """Orchestrates API test suite execution with assertion evaluation."""

    registry: ProviderRegistry
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("testcode.api_test_orchestrator")
    )

    # ------------------------------------------------------------------
    # public pipeline
    # ------------------------------------------------------------------

    def execute_api_test(
        self,
        suite: ApiTestSuite,
        *,
        use_coze_enrichment: bool = False,
        coze_bot_id: str | None = None,
        coze_user_id: str | None = None,
        use_n8n: bool = False,
        n8n_webhook_url: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> dict[str, Any]:
        """Execute the API test pipeline and return structured results.

        Args:
            suite: The API test suite to execute.
            use_coze_enrichment: If True, enrich suite via Coze before execution.
            coze_bot_id: Coze bot ID (required if use_coze_enrichment=True).
            coze_user_id: Coze user ID (required if use_coze_enrichment=True).
            use_n8n: If True, route execution through n8n instead of local HTTP.
            n8n_webhook_url: n8n webhook URL (required if use_n8n=True).
            http_client: Optional httpx.Client for testing (stub transport).

        Returns a dict with keys: ``suite``, ``results``, ``report``.
        """
        if not suite.endpoints:
            raise ValueError("ApiTestSuite must contain at least one endpoint")

        # --- optional Coze enrichment ---
        if use_coze_enrichment:
            coze = self.registry.get("coze")
            suite = self._enrich_with_coze(coze, suite, coze_bot_id, coze_user_id)

        # --- optional n8n-based execution ---
        if use_n8n:
            if not n8n_webhook_url:
                raise ValueError("n8n_webhook_url is required when use_n8n=True")
            n8n = self.registry.get("n8n")
            return self._execute_via_n8n(n8n, suite, n8n_webhook_url)

        # --- local HTTP execution ---
        start_time = time.monotonic()
        results: list[ApiExecutionResult] = []

        close_on_exit = http_client is None
        if http_client is None:
            http_client = httpx.Client(timeout=30.0)

        try:
            for endpoint in suite.endpoints:
                self.logger.info(
                    "Executing API endpoint",
                    extra={"endpoint_id": endpoint.endpoint_id, "method": endpoint.method, "url": endpoint.url},
                )
                result = self._execute_endpoint(endpoint, suite.base_url, http_client)
                results.append(result)
        finally:
            if close_on_exit:
                http_client.close()

        total_duration_ms = (time.monotonic() - start_time) * 1000
        report = self._build_api_report(suite, results, total_duration_ms)

        self.logger.info(
            "API test suite complete",
            extra={"request_id": suite.request_id, "passed": report.passed, "failed": report.failed},
        )

        return {"suite": suite, "results": results, "report": report}

    # ------------------------------------------------------------------
    # endpoint execution
    # ------------------------------------------------------------------

    def _execute_endpoint(
        self, endpoint: ApiEndpoint, base_url: str, http_client: httpx.Client
    ) -> ApiExecutionResult:
        """Execute a single API endpoint and return the result."""
        full_url = base_url.rstrip("/") + "/" + endpoint.url.lstrip("/") if base_url else endpoint.url
        start = time.monotonic()

        try:
            # Determine body serialisation: dict/list → json, str/bytes → content
            body_is_json = endpoint.body is not None and isinstance(endpoint.body, (dict, list))
            body_is_raw = endpoint.body is not None and isinstance(endpoint.body, (str, bytes))
            response = http_client.request(
                method=endpoint.method.value,
                url=full_url,
                params=endpoint.query_params or None,
                headers=endpoint.headers or None,
                json=endpoint.body if body_is_json else None,
                content=endpoint.body if body_is_raw else None,
            )
            response_time_ms = (time.monotonic() - start) * 1000

            response_body = None
            try:
                response_body = response.json()
            except (json.JSONDecodeError, ValueError):
                response_body = response.text

            response_headers = dict(response.headers)

            # Build context dict for assertion evaluation
            assertion_context: dict[str, Any] = {
                "status_code": response.status_code,
                "headers": response_headers,
                "body": response_body,
            }

            # Evaluate assertions
            assertion_results = self._evaluate_assertions(endpoint, assertion_context)

            # Determine pass/fail
            status_ok = response.status_code == endpoint.expected_status
            assertions_ok = all(a.passed for a in assertion_results)
            passed = status_ok and assertions_ok

            return ApiExecutionResult(
                endpoint_id=endpoint.endpoint_id,
                url=full_url,
                method=endpoint.method.value,
                status_code=response.status_code,
                response_body=response_body,
                response_headers=response_headers,
                response_time_ms=round(response_time_ms, 2),
                assertions=assertion_results,
                passed=passed,
                error_message=None if passed else self._failure_reason(status_ok, assertion_results),
            )

        except httpx.RequestError as exc:
            response_time_ms = (time.monotonic() - start) * 1000
            return ApiExecutionResult(
                endpoint_id=endpoint.endpoint_id,
                url=full_url,
                method=endpoint.method.value,
                status_code=0,
                response_body=None,
                response_headers={},
                response_time_ms=round(response_time_ms, 2),
                assertions=[],
                passed=False,
                error_message=f"Request failed: {exc}",
            )
        except Exception as exc:
            response_time_ms = (time.monotonic() - start) * 1000
            self.logger.exception("Unexpected error executing endpoint")
            return ApiExecutionResult(
                endpoint_id=endpoint.endpoint_id,
                url=full_url,
                method=endpoint.method.value,
                status_code=0,
                response_body=None,
                response_headers={},
                response_time_ms=round(response_time_ms, 2),
                assertions=[],
                passed=False,
                error_message=f"Unexpected error: {exc}",
            )

    # ------------------------------------------------------------------
    # assertion evaluation
    # ------------------------------------------------------------------

    def _evaluate_assertions(
        self, endpoint: ApiEndpoint, context: dict[str, Any]
    ) -> list[ApiResponseAssertion]:
        """Evaluate all assertions defined on an endpoint."""
        results: list[ApiResponseAssertion] = []

        # Always check expected_status unless user already has a status assertion
        for assertion_spec in endpoint.assertions:
            path = assertion_spec.get("path", "")
            operator = assertion_spec.get("operator", "equals")
            expected = assertion_spec.get("expected")

            actual = _resolve_jsonpath(context, path)
            passed = _evaluate_operator(actual, operator, expected)

            results.append(
                ApiResponseAssertion(
                    path=path,
                    operator=operator,
                    expected=expected,
                    actual=actual,
                    passed=passed,
                    message=None if passed else f"Expected {expected}, got {actual}",
                )
            )

        return results

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _failure_reason(
        self, status_ok: bool, assertions: list[ApiResponseAssertion]
    ) -> str:
        """Build a human-readable failure reason."""
        parts: list[str] = []
        if not status_ok:
            parts.append("Status code mismatch")
        failed = [a for a in assertions if not a.passed]
        if failed:
            parts.append(f"{len(failed)} assertion(s) failed")
        return "; ".join(parts)

    def _build_api_report(
        self,
        suite: ApiTestSuite,
        results: list[ApiExecutionResult],
        total_duration_ms: float,
    ) -> ApiTestReport:
        """Build a summary report from execution results."""
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        avg_ms = (
            sum(r.response_time_ms for r in results) / len(results) if results else 0.0
        )

        issues: list[str] = []
        highlights: list[str] = []
        risk_level = "P3"

        if failed > 0:
            for r in results:
                if not r.passed:
                    issues.append(f"{r.method} {r.url} - {r.error_message or 'assertion failed'}")
            risk_level = "P0" if failed > len(results) / 2 else "P2"
        else:
            highlights.append("All endpoints passed")

        if avg_ms > 500:
            issues.append(f"Average response time ({avg_ms:.0f}ms) exceeds 500ms threshold")
            risk_level = "P2" if risk_level == "P3" else risk_level

        highlights.append(f"{passed}/{len(results)} endpoints passed")
        highlights.append(f"Total duration: {total_duration_ms:.0f}ms")

        return ApiTestReport(
            request_id=suite.request_id,
            suite_name=suite.suite_name,
            total_endpoints=len(results),
            passed=passed,
            failed=failed,
            total_duration_ms=round(total_duration_ms, 2),
            avg_response_time_ms=round(avg_ms, 2),
            results=results,
            issues=issues if failed > 0 else [],
            highlights=highlights,
            risk_level=risk_level,
        )

    # ------------------------------------------------------------------
    # optional Coze enrichment
    # ------------------------------------------------------------------

    def _enrich_with_coze(
        self,
        coze_client: Any,
        suite: ApiTestSuite,
        bot_id: str | None,
        user_id: str | None,
    ) -> ApiTestSuite:
        """Use Coze to suggest additional assertions."""
        if not bot_id or not user_id:
            self.logger.warning("Coze enrichment requested but bot_id/user_id not provided")
            return suite
        try:
            endpoint_summaries = [
                f"{e.method.value} {e.url} (expected status: {e.expected_status})"
                for e in suite.endpoints
            ]
            query = "Given these endpoints, suggest additional test assertions:\n" + "\n".join(
                endpoint_summaries
            )
            coze_client.chat(bot_id=bot_id, user_id=user_id, query=query)
            self.logger.info("Coze enrichment completed", extra={"request_id": suite.request_id})
        except Exception as exc:
            self.logger.warning("Coze enrichment failed", extra={"error": str(exc)})
        return suite

    # ------------------------------------------------------------------
    # optional n8n-based execution
    # ------------------------------------------------------------------

    def _execute_via_n8n(
        self, n8n_client: Any, suite: ApiTestSuite, webhook_url: str
    ) -> dict[str, Any]:
        """Route API test execution through an n8n workflow."""
        payload = suite.model_dump()
        trigger_result = n8n_client.trigger_workflow(webhook_url, payload)

        results: list[ApiExecutionResult] = []
        if trigger_result.execution_id:
            trigger_result = n8n_client.wait_for_completion(trigger_result.execution_id)

        raw_data = getattr(trigger_result, "raw", {}) or {}
        for ep_data in raw_data.get("results", []):
            results.append(ApiExecutionResult(**ep_data) if isinstance(ep_data, dict) else ep_data)

        total_duration_ms = float(raw_data.get("duration_ms", 0))
        report = self._build_api_report(suite, results, total_duration_ms)

        return {"suite": suite, "results": results, "report": report}
