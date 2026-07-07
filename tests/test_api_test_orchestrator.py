"""Unit tests for ApiTestOrchestrator."""

from __future__ import annotations

import httpx
import pytest

from testcode.adapters.coze import CozeClient
from testcode.adapters.dify import DifyClient
from testcode.adapters.n8n import N8nClient
from testcode.api_test_orchestrator import ApiTestOrchestrator, _evaluate_operator, _resolve_jsonpath
from testcode.models.api_test import ApiEndpoint, ApiTestSuite, HttpMethod
from testcode.providers.registry import ProviderRegistry


class StubTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


# ---------------------------------------------------------------------------
# JSONPath resolver tests
# ---------------------------------------------------------------------------


class TestJsonPathResolver:
    def test_resolve_root(self) -> None:
        data = {"a": 1}
        assert _resolve_jsonpath(data, "$") == data

    def test_resolve_empty(self) -> None:
        data = {"a": 1}
        assert _resolve_jsonpath(data, "") == data

    def test_resolve_nested(self) -> None:
        data = {"data": {"id": 42, "name": "test"}}
        assert _resolve_jsonpath(data, "$.data.id") == 42
        assert _resolve_jsonpath(data, "$.data.name") == "test"

    def test_resolve_status_code(self) -> None:
        context = {"status_code": 200, "body": {}}
        assert _resolve_jsonpath(context, "status_code") == 200

    def test_resolve_nonexistent(self) -> None:
        assert _resolve_jsonpath({}, "$.missing.key") is None
        assert _resolve_jsonpath({"a": 1}, "$.b") is None

    def test_resolve_list_index(self) -> None:
        data = {"items": [{"name": "a"}, {"name": "b"}]}
        assert _resolve_jsonpath(data, "$.items[0].name") == "a"
        assert _resolve_jsonpath(data, "$.items[1].name") == "b"

    def test_resolve_list_index_out_of_range(self) -> None:
        data = {"items": [{"name": "a"}]}
        assert _resolve_jsonpath(data, "$.items[5].name") is None


# ---------------------------------------------------------------------------
# Operator tests
# ---------------------------------------------------------------------------


class TestOperatorEvaluation:
    def test_equals(self) -> None:
        assert _evaluate_operator(200, "equals", 200) is True
        assert _evaluate_operator(200, "equals", 404) is False

    def test_contains_string(self) -> None:
        assert _evaluate_operator("hello world", "contains", "world") is True
        assert _evaluate_operator("hello", "contains", "x") is False

    def test_contains_list(self) -> None:
        assert _evaluate_operator([1, 2, 3], "contains", 2) is True
        assert _evaluate_operator([1, 2, 3], "contains", 5) is False

    def test_matches_regex(self) -> None:
        assert _evaluate_operator("abc123", "matches_regex", r"\d+") is True
        assert _evaluate_operator("abc", "matches_regex", r"\d+") is False

    def test_less_than(self) -> None:
        assert _evaluate_operator(100, "less_than", 500) is True
        assert _evaluate_operator(500, "less_than", 100) is False

    def test_greater_than(self) -> None:
        assert _evaluate_operator(500, "greater_than", 100) is True
        assert _evaluate_operator(100, "greater_than", 500) is False


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_stub_registry(handler) -> ProviderRegistry:
    """Create a ProviderRegistry where all HTTP clients use the same stub transport."""
    transport = StubTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://test.example.com")
    return ProviderRegistry(
        coze=CozeClient(access_token="token", client=http),
        dify=DifyClient(api_key="key", client=http),
        n8n=N8nClient(base_url="https://n8n.example.com/api", client=http),
    )


def _api_handler(request: httpx.Request) -> httpx.Response:
    """Default handler: all endpoints return 200 OK."""
    return httpx.Response(200, json={"status": "ok", "data": {"id": 1}})


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------


def test_execute_api_test_success() -> None:
    """Execute API test against stub endpoints — all should pass."""
    registry = _make_stub_registry(_api_handler)

    suite = ApiTestSuite(
        request_id="req-1",
        suite_name="Test Suite",
        base_url="https://test.example.com",
        endpoints=[
            ApiEndpoint(endpoint_id="ep-1", name="Get Items", method=HttpMethod.GET, url="/items"),
            ApiEndpoint(endpoint_id="ep-2", name="Create Item", method=HttpMethod.POST, url="/items", body={"name": "test"}),
        ],
    )

    orch = ApiTestOrchestrator(registry=registry)
    stub_client = httpx.Client(
        transport=StubTransport(_api_handler), base_url="https://test.example.com"
    )
    result = orch.execute_api_test(suite, http_client=stub_client)

    assert result["report"].total_endpoints == 2
    assert result["report"].passed == 2
    assert result["report"].failed == 0
    assert len(result["results"]) == 2


def test_execute_api_test_with_failure() -> None:
    """One endpoint returns unexpected status -> should be marked failed."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "/fail" in str(request.url):
            return httpx.Response(500, json={"error": "internal"})
        return httpx.Response(200, json={"ok": True})

    registry = _make_stub_registry(handler)

    suite = ApiTestSuite(
        request_id="req-2",
        suite_name="Mixed Suite",
        base_url="https://test.example.com",
        endpoints=[
            ApiEndpoint(endpoint_id="ep-1", name="Good", method=HttpMethod.GET, url="/good"),
            ApiEndpoint(endpoint_id="ep-2", name="Bad", method=HttpMethod.GET, url="/fail"),
        ],
    )

    orch = ApiTestOrchestrator(registry=registry)
    stub_client = httpx.Client(
        transport=StubTransport(handler), base_url="https://test.example.com"
    )
    result = orch.execute_api_test(suite, http_client=stub_client)

    assert result["report"].total_endpoints == 2
    assert result["report"].passed == 1
    assert result["report"].failed == 1


def test_execute_api_test_empty_suite_raises() -> None:
    """Empty endpoints should raise ValueError."""
    registry = _make_stub_registry(_api_handler)
    suite = ApiTestSuite(request_id="req-3", suite_name="Empty", endpoints=[])

    orch = ApiTestOrchestrator(registry=registry)
    with pytest.raises(ValueError, match="at least one endpoint"):
        orch.execute_api_test(suite)


def test_api_assertion_evaluation() -> None:
    """Assertions defined on endpoints are evaluated."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"id": 42, "name": "test-item"}})

    registry = _make_stub_registry(handler)

    suite = ApiTestSuite(
        request_id="req-4",
        suite_name="Assertion Suite",
        base_url="https://test.example.com",
        endpoints=[
            ApiEndpoint(
                endpoint_id="ep-1",
                name="Check Data",
                method=HttpMethod.GET,
                url="/data",
                assertions=[
                    {"path": "status_code", "operator": "equals", "expected": 200},
                    {"path": "$.body.data.id", "operator": "equals", "expected": 42},
                ],
            ),
        ],
    )

    orch = ApiTestOrchestrator(registry=registry)
    stub_client = httpx.Client(
        transport=StubTransport(handler), base_url="https://test.example.com"
    )
    result = orch.execute_api_test(suite, http_client=stub_client)

    assert result["report"].passed == 1
    assert len(result["results"][0].assertions) == 2
    assert all(a.passed for a in result["results"][0].assertions)


def test_execute_api_test_via_n8n() -> None:
    """Test routing execution through n8n."""

    def n8n_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"executionId": "exec-99", "status": "running"})
        return httpx.Response(200, json={"status": "success", "data": {"duration_ms": 150, "results": []}})

    n8n_transport = StubTransport(n8n_handler)
    n8n_http = httpx.Client(transport=n8n_transport, base_url="https://n8n.example.com/api")

    def generic_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    registry = _make_stub_registry(generic_handler)
    # Replace n8n with the properly stubbed one
    registry = ProviderRegistry(
        coze=registry.coze,
        dify=registry.dify,
        n8n=N8nClient(base_url="https://n8n.example.com/api", client=n8n_http),
    )

    suite = ApiTestSuite(
        request_id="req-n8n",
        suite_name="N8N Suite",
        base_url="https://test.example.com",
        endpoints=[ApiEndpoint(endpoint_id="ep-1", name="Test", method=HttpMethod.GET, url="/test")],
    )

    orch = ApiTestOrchestrator(registry=registry)
    result = orch.execute_api_test(suite, use_n8n=True, n8n_webhook_url="https://n8n.example.com/webhook/test")

    assert "report" in result


def test_api_orchestrator_report_fields() -> None:
    """Report fields are computed correctly."""
    registry = _make_stub_registry(_api_handler)

    suite = ApiTestSuite(
        request_id="req-report",
        suite_name="Report Suite",
        base_url="https://test.example.com",
        endpoints=[
            ApiEndpoint(endpoint_id="ep-1", name="A", method=HttpMethod.GET, url="/a"),
            ApiEndpoint(endpoint_id="ep-2", name="B", method=HttpMethod.GET, url="/b"),
            ApiEndpoint(endpoint_id="ep-3", name="C", method=HttpMethod.GET, url="/c"),
        ],
    )

    orch = ApiTestOrchestrator(registry=registry)
    stub_client = httpx.Client(
        transport=StubTransport(_api_handler), base_url="https://test.example.com"
    )
    result = orch.execute_api_test(suite, http_client=stub_client)

    report = result["report"]
    assert report.total_endpoints == 3
    assert report.passed + report.failed == 3
    assert report.total_duration_ms > 0
    assert report.avg_response_time_ms > 0
    assert report.risk_level in ("low", "medium", "high")


def test_execute_endpoint_connection_error() -> None:
    """Connection errors produce a failed result, not an exception."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    registry = _make_stub_registry(handler)

    suite = ApiTestSuite(
        request_id="req-err",
        suite_name="Error Suite",
        base_url="https://test.example.com",
        endpoints=[ApiEndpoint(endpoint_id="ep-1", name="Bad", method=HttpMethod.GET, url="/bad")],
    )

    orch = ApiTestOrchestrator(registry=registry)
    stub_client = httpx.Client(
        transport=StubTransport(handler), base_url="https://test.example.com"
    )
    result = orch.execute_api_test(suite, http_client=stub_client)

    assert result["report"].failed == 1
    assert result["results"][0].error_message is not None
    assert "Connection refused" in result["results"][0].error_message
