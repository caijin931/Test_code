from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import typer

from testcode.app import build_orchestrator
from testcode.models import TestRequirement
from testcode.test_orchestrator import TestOrchestrator

app = typer.Typer(add_completion=False)


@app.command()
def health(settings: Path | None = typer.Option(None, "--settings", exists=True, dir_okay=False)) -> None:
    orchestrator = build_orchestrator(settings)
    typer.echo(orchestrator.health_check())


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
    orchestrator = build_orchestrator(settings)
    workflow = TestRequirement(request_id="cli-workflow", requirement=coze_query)
    result = {
        "coze_bot_id": coze_bot_id,
        "coze_user_id": coze_user_id,
        "coze_query": workflow.requirement,
        "dify_user": dify_user,
        "n8n_webhook_url": n8n_webhook_url,
        "wait": wait,
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
    requirement_text = requirement_file.read_text(encoding="utf-8").strip() if requirement_file else requirement
    flow = TestOrchestrator(registry=orchestrator.registry)
    result = flow.execute_test_flow(
        TestRequirement(request_id="cli-test-flow", requirement=requirement_text),
        n8n_webhook_url,
    )
    payload = _to_jsonable(result)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)
    typer.echo(rendered)
    if output:
        output.write_text(rendered, encoding="utf-8")


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value
