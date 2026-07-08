from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TestRequirement(BaseModel):
    request_id: str
    requirement: str
    product_name: str | None = None
    module_name: str | None = None
    test_type: str = "ui"  # "ui", "api", or "perf"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    assertion_rules: list[dict[str, Any]] = Field(default_factory=list)


class TestStep(BaseModel):
    step_no: int
    action: str
    expected_result: str
    data: dict[str, Any] = Field(default_factory=dict)


class TestCase(BaseModel):
    case_id: str
    title: str
    preconditions: list[str] = Field(default_factory=list)
    steps: list[TestStep] = Field(default_factory=list)
    priority: str = "medium"
    severity: str = "normal"
    tags: list[str] = Field(default_factory=list)


class TestCaseBundle(BaseModel):
    request_id: str
    cases: list[TestCase]
    raw: dict[str, Any] = Field(default_factory=dict)


class CozeEnrichment(BaseModel):
    request_id: str
    datasource: str | None = None
    test_data: dict[str, Any] = Field(default_factory=dict)
    browser_hints: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class AssertionResult(BaseModel):
    name: str
    expected: Any
    actual: Any
    passed: bool = True
    message: str | None = None


class AssertionSuite(BaseModel):
    items: list[AssertionResult] = Field(default_factory=list)


class AutomationPayload(BaseModel):
    request_id: str
    suite_name: str
    cases: list[TestCase]
    test_data: dict[str, Any] = Field(default_factory=dict)
    browser_hints: dict[str, Any] = Field(default_factory=dict)
    execution_mode: str = "playwright"
    env: dict[str, Any] = Field(default_factory=dict)
    assertion_rules: list[dict[str, Any]] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    request_id: str
    execution_id: str | None = None
    status: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float | None = None
    artifacts: list[str] = Field(default_factory=list)
    assertions: AssertionSuite = Field(default_factory=AssertionSuite)
    raw: dict[str, Any] = Field(default_factory=dict)


class TestReport(BaseModel):
    request_id: str
    summary: str
    risk_level: str = "P2"
    highlights: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
