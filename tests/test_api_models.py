"""Unit tests for API testing Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from testcode.models import (
    ApiEndpoint,
    ApiExecutionResult,
    ApiResponseAssertion,
    ApiTestReport,
    ApiTestSuite,
    HttpMethod,
)


def test_api_endpoint_validation() -> None:
    """An ApiEndpoint requires endpoint_id, name, method, url."""
    endpoint = ApiEndpoint(
        endpoint_id="ep-1",
        name="Get Users",
        method=HttpMethod.GET,
        url="/api/users",
    )
    assert endpoint.method == HttpMethod.GET
    assert endpoint.expected_status == 200
    assert endpoint.assertions == []


def test_api_endpoint_defaults() -> None:
    """Default values are populated correctly."""
    endpoint = ApiEndpoint(
        endpoint_id="ep-2",
        name="Create Item",
        method=HttpMethod.POST,
        url="/api/items",
        body={"name": "test"},
    )
    assert endpoint.path_params == {}
    assert endpoint.query_params == {}
    assert endpoint.headers == {}
    assert endpoint.expected_schema == {}
    assert endpoint.tags == []


def test_api_endpoint_invalid_method_raises() -> None:
    """Invalid HTTP method should raise ValidationError."""
    with pytest.raises(ValidationError):
        ApiEndpoint(
            endpoint_id="ep-3",
            name="Bad Method",
            method="INVALID",  # type: ignore[arg-type]
            url="/api/test",
        )


def test_api_suite_holds_endpoints() -> None:
    """ApiTestSuite holds a list of ApiEndpoints."""
    suite = ApiTestSuite(
        request_id="req-1",
        suite_name="User Service",
        base_url="https://api.example.com",
        endpoints=[
            ApiEndpoint(endpoint_id="ep-1", name="List Users", method=HttpMethod.GET, url="/users"),
            ApiEndpoint(endpoint_id="ep-2", name="Get User", method=HttpMethod.GET, url="/users/1"),
        ],
    )
    assert len(suite.endpoints) == 2
    assert suite.base_url == "https://api.example.com"


def test_api_suite_empty_endpoints() -> None:
    """Suite can be created with empty endpoints list."""
    suite = ApiTestSuite(
        request_id="req-2",
        suite_name="Empty Suite",
        endpoints=[],
    )
    assert len(suite.endpoints) == 0


def test_api_response_assertion_defaults() -> None:
    """ApiResponseAssertion defaults are correct."""
    assertion = ApiResponseAssertion(
        path="$.data.id",
        operator="equals",
        expected=42,
    )
    assert assertion.actual is None
    assert assertion.passed is False
    assert assertion.message is None


def test_api_response_assertion_passed() -> None:
    """ApiResponseAssertion with passed=True stores correct values."""
    assertion = ApiResponseAssertion(
        path="$.status",
        operator="equals",
        expected="ok",
        actual="ok",
        passed=True,
        message="Status matches",
    )
    assert assertion.passed is True
    assert assertion.actual == "ok"


def test_api_execution_result_defaults() -> None:
    """ApiExecutionResult has sensible defaults."""
    result = ApiExecutionResult(
        endpoint_id="ep-1",
        url="/users",
        method="GET",
        status_code=200,
        response_time_ms=45.2,
    )
    assert result.response_body is None
    assert result.response_headers == {}
    assert result.assertions == []
    assert result.passed is False
    assert result.error_message is None


def test_api_execution_result_success() -> None:
    """ApiExecutionResult for a successful test."""
    assertion = ApiResponseAssertion(
        path="status_code",
        operator="equals",
        expected=200,
        actual=200,
        passed=True,
    )
    result = ApiExecutionResult(
        endpoint_id="ep-1",
        url="/users",
        method="GET",
        status_code=200,
        response_time_ms=45.2,
        assertions=[assertion],
        passed=True,
    )
    assert result.passed is True
    assert len(result.assertions) == 1


def test_api_test_report_aggregates() -> None:
    """ApiTestReport correctly tracks pass/fail counts."""
    report = ApiTestReport(
        request_id="req-1",
        suite_name="User Service",
        total_endpoints=5,
        passed=4,
        failed=1,
        total_duration_ms=320.5,
        avg_response_time_ms=64.1,
        results=[],
    )
    assert report.total_endpoints == 5
    assert report.passed + report.failed == report.total_endpoints
    assert report.risk_level == "P2"


def test_api_test_report_with_issues() -> None:
    """ApiTestReport can hold issues and highlights."""
    report = ApiTestReport(
        request_id="req-2",
        suite_name="Fail Suite",
        total_endpoints=3,
        passed=1,
        failed=2,
        total_duration_ms=500.0,
        avg_response_time_ms=166.7,
        results=[],
        issues=["Endpoint /login returned 500", "Timeout on /search"],
        highlights=["/health passed"],
        risk_level="P0",
    )
    assert len(report.issues) == 2
    assert len(report.highlights) == 1
    assert report.risk_level == "P0"
