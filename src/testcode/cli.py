from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import typer

from testcode.api_test_orchestrator import ApiTestOrchestrator
from testcode.app import build_orchestrator
from testcode.models import TestRequirement
from testcode.models.api_test import ApiEndpoint, ApiTestSuite
from testcode.models.perf_test import LoadPattern, PerformanceProfile
from testcode.perf_test_orchestrator import PerfTestOrchestrator
from testcode.test_orchestrator import TestOrchestrator

app = typer.Typer(add_completion=False)


@app.command()
def health(settings: Path | None = typer.Option(None, "--settings", exists=True, dir_okay=False)) -> None:
    orchestrator = build_orchestrator(settings)
    typer.echo(json.dumps(orchestrator.health_check(), ensure_ascii=False, indent=2))


@app.command()
def cache_health(settings: Path | None = typer.Option(None, "--settings", exists=True, dir_okay=False)) -> None:
    orchestrator = build_orchestrator(settings)
    dify = orchestrator.registry.get("dify")
    summary = {
        "provider": "dify",
        "client_type": type(dify).__name__,
        "cache_enabled": type(dify).__name__.startswith("Cached"),
    }
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))


@app.command()
def run(
    settings: Path | None = typer.Option(None, "--settings", exists=True, dir_okay=False),
    coze_bot_id: str = typer.Option(..., "--coze-bot-id"),
    coze_user_id: str = typer.Option(..., "--coze-user-id"),
    coze_query: str = typer.Option(..., "--coze-query"),
    dify_user: str = typer.Option(..., "--dify-user"),
    n8n_webhook_url: str = typer.Option(..., "--n8n-webhook-url"),
    wait: bool = typer.Option(False, "--wait", help="Wait for n8n execution to complete"),
) -> None:
    build_orchestrator(settings)
    workflow = TestRequirement(request_id="cli-workflow", requirement=coze_query)
    result = {
        "coze_bot_id": coze_bot_id,
        "coze_user_id": coze_user_id,
        "coze_query": workflow.requirement,
        "dify_user": dify_user,
        "n8n_webhook_url": n8n_webhook_url,
        "wait": wait,
        "status": "ready",
    }
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def run_test_flow(
    requirement: str = typer.Option(..., "--requirement"),
    settings: Path | None = typer.Option(None, "--settings", exists=True, dir_okay=False),
    requirement_file: Path | None = typer.Option(None, "--requirement-file", exists=True, dir_okay=False),
    n8n_webhook_url: str = typer.Option(..., "--n8n-webhook-url"),
    output: Path | None = typer.Option(None, "--output", dir_okay=False),
    pretty: bool = typer.Option(True, "--pretty/--compact"),
) -> None:
    orchestrator = build_orchestrator(settings)
    requirement_text = requirement_file.read_text(encoding="utf-8").strip() if requirement_file else requirement.strip()
    if not requirement_text:
        raise typer.BadParameter("requirement must not be empty")
    if not n8n_webhook_url.strip():
        raise typer.BadParameter("n8n_webhook_url must not be empty")

    flow = TestOrchestrator(registry=orchestrator.registry)
    typer.echo("[1/4] 生成测试流...")
    result = flow.execute_test_flow(
        TestRequirement(request_id="cli-test-flow", requirement=requirement_text),
        n8n_webhook_url.strip(),
    )
    typer.echo("[2/4] 生成结果中...")
    payload = _to_jsonable(result)
    typer.echo("[3/4] 整理输出中...")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)
    typer.echo("[4/4] 完成")
    typer.echo(rendered)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")


@app.command()
def api_test(
    settings: Path | None = typer.Option(None, "--settings", exists=True, dir_okay=False),
    suite_name: str = typer.Option(..., "--suite-name"),
    base_url: str = typer.Option(..., "--base-url"),
    endpoints_file: Path = typer.Option(..., "--endpoints-file", exists=True, dir_okay=False),
    use_n8n: bool = typer.Option(False, "--use-n8n"),
    n8n_webhook_url: str = typer.Option("", "--n8n-webhook-url"),
    output: Path | None = typer.Option(None, "--output", dir_okay=False),
    pretty: bool = typer.Option(True, "--pretty/--compact"),
) -> None:
    """Execute API / interface tests against HTTP endpoints."""
    orchestrator = build_orchestrator(settings)

    raw = json.loads(endpoints_file.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        endpoints = [ApiEndpoint(**ep) for ep in raw]
    elif isinstance(raw, dict):
        if "endpoints" in raw:
            endpoints = [ApiEndpoint(**ep) for ep in raw["endpoints"]]
        else:
            raise typer.BadParameter(
                "endpoints_file must be a JSON array of endpoints or a JSON object "
                'with an "endpoints" key'
            )
    else:
        raise typer.BadParameter("endpoints_file must be a JSON array or object")

    suite = ApiTestSuite(
        request_id="cli-api-test",
        suite_name=suite_name,
        base_url=base_url,
        endpoints=endpoints,
    )

    api_orchestrator = ApiTestOrchestrator(registry=orchestrator.registry)
    typer.echo("[1/3] 执行接口测试...")
    result = api_orchestrator.execute_api_test(
        suite,
        use_n8n=use_n8n,
        n8n_webhook_url=n8n_webhook_url if use_n8n else None,
    )
    typer.echo("[2/3] 生成报告...")
    payload = _to_jsonable(result)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)
    typer.echo("[3/3] 完成")
    typer.echo(rendered)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")


@app.command()
def perf_test(
    settings: Path | None = typer.Option(None, "--settings", exists=True, dir_okay=False),
    target_url: str = typer.Option(..., "--target-url"),
    profile_name: str = typer.Option("cli-perf-test", "--profile-name"),
    method: str = typer.Option("GET", "--method"),
    load_pattern: str = typer.Option("constant", "--load-pattern"),
    concurrency: int = typer.Option(10, "--concurrency"),
    duration: int = typer.Option(60, "--duration"),
    ramp_up: int = typer.Option(0, "--ramp-up"),
    output: Path | None = typer.Option(None, "--output", dir_okay=False),
    pretty: bool = typer.Option(True, "--pretty/--compact"),
) -> None:
    """Execute performance / load test against a target URL."""
    orchestrator = build_orchestrator(settings)

    try:
        pattern = LoadPattern(load_pattern.lower())
    except ValueError:
        raise typer.BadParameter(f"Invalid load pattern: {load_pattern}. Use one of: constant, ramp_up, spike, soak")

    valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    method_upper = method.upper()
    if method_upper not in valid_methods:
        raise typer.BadParameter(
            f"Invalid HTTP method: {method}. Use one of: {', '.join(sorted(valid_methods))}"
        )

    profile = PerformanceProfile(
        request_id="cli-perf-test",
        profile_name=profile_name,
        target_url=target_url,
        method=method_upper,
        load_pattern=pattern,
        concurrency=concurrency,
        duration_seconds=duration,
        ramp_up_seconds=ramp_up,
    )

    perf_orchestrator = PerfTestOrchestrator(registry=orchestrator.registry)
    typer.echo(f"[1/3] 启动性能测试 (并发: {concurrency}, 时长: {duration}s)...")
    result = perf_orchestrator.execute_perf_test(profile)
    typer.echo("[2/3] 生成报告...")
    payload = _to_jsonable(result)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)
    typer.echo("[3/3] 完成")
    typer.echo(rendered)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value
