"""Pydantic models for API / interface testing."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HttpMethod(str, Enum):
    """HTTP methods supported for API testing."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ApiEndpoint(BaseModel):
    """A single API endpoint to test, analogous to TestStep for HTTP."""

    endpoint_id: str
    name: str
    method: HttpMethod
    url: str
    path_params: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    expected_status: int = 200
    expected_schema: dict[str, Any] = Field(default_factory=dict)
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ApiTestSuite(BaseModel):
    """A collection of API endpoints grouped by service/domain."""

    request_id: str
    suite_name: str
    base_url: str = ""
    endpoints: list[ApiEndpoint]
    env: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ApiResponseAssertion(BaseModel):
    """Assertion on a single HTTP response field."""

    path: str  # JSONPath or header name, e.g. "$.data.id", "status_code"
    operator: str  # "equals", "contains", "matches_regex", "less_than", "greater_than"
    expected: Any
    actual: Any = None
    passed: bool = False
    message: str | None = None


class ApiExecutionResult(BaseModel):
    """Result of executing a single API endpoint test."""

    endpoint_id: str
    url: str
    method: str
    status_code: int
    response_body: Any = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_time_ms: float = 0.0
    assertions: list[ApiResponseAssertion] = Field(default_factory=list)
    passed: bool = False
    error_message: str | None = None


class ApiTestReport(BaseModel):
    """Summary report for an API test suite execution."""

    request_id: str
    suite_name: str
    total_endpoints: int
    passed: int
    failed: int
    total_duration_ms: float
    avg_response_time_ms: float
    results: list[ApiExecutionResult]
    issues: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    risk_level: str = "P2"
    raw: dict[str, Any] = Field(default_factory=dict)
