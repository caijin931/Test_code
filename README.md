# Testcode

[![CI](https://github.com/caijin931/Test_code/actions/workflows/ci.yml/badge.svg)](https://github.com/caijin931/Test_code/actions/workflows/ci.yml)

Testcode is a Python-first orchestration scaffold for coordinating test automation across Dify, Coze, and n8n.

## Overview

The project provides:

- a shared Python control plane for test generation and execution
- provider adapters for Dify, Coze, and n8n
- a test-oriented orchestrator for generating test cases, enriching them with external data, and triggering automation
- a CLI for end-to-end execution
- caching, configuration, Docker packaging, and CI support

## Installation

### Local development

1. Create and activate a Python 3.11+ virtual environment.
2. Install the project with development dependencies:

```bash
pip install -e .[dev]
```

If `PyYAML` is not installed, the app can still parse the example settings file using a built-in fallback parser, but installing the normal dependencies is strongly recommended.

### Docker

Build the image:

```bash
docker build -t testcode:latest .
```

Run the container with a settings file mounted into the container:

```bash
docker run --rm \
  -e TESTCODE_COZE_ACCESS_TOKEN=your-token \
  -e TESTCODE_DIFY_API_KEY=your-key \
  -v ${PWD}/config:/app/config \
  testcode:latest health --settings config/settings.example.yaml
```

### Docker Compose

Copy the example environment file and adjust it for your local setup:

```bash
cp .env.example .env
```

Start the app with Redis and an optional n8n service:

```bash
docker compose up --build
```

The compose stack exposes:

- `app` — the Testcode CLI/runtime container
- `redis` — optional cache backend for Dify caching
- `n8n` — local workflow engine for webhook-triggered automation

## Configuration

Use `config/settings.example.yaml` as the starting point for local or containerized setups.

### Core settings

- `coze.access_token`
- `coze.base_url`
- `coze.timeout_seconds`
- `dify.api_key`
- `dify.base_url`
- `dify.timeout_seconds`
- `n8n.base_url`
- `n8n.timeout_seconds`

### Cache settings

- `dify.cache_enabled`
- `dify.cache_directory`
- `dify.cache_ttl_seconds`
- `dify.cache_backend`
- `dify.cache_redis_url`
- `dify.cache_redis_prefix`

### Environment variables

The default prefix is `TESTCODE_`.

- `TESTCODE_COZE_ACCESS_TOKEN`
- `TESTCODE_COZE_BASE_URL`
- `TESTCODE_COZE_TIMEOUT_SECONDS`
- `TESTCODE_DIFY_API_KEY`
- `TESTCODE_DIFY_BASE_URL`
- `TESTCODE_DIFY_TIMEOUT_SECONDS`
- `TESTCODE_DIFY_CACHE_ENABLED`
- `TESTCODE_DIFY_CACHE_DIRECTORY`
- `TESTCODE_DIFY_CACHE_TTL_SECONDS`
- `TESTCODE_DIFY_CACHE_BACKEND`
- `TESTCODE_DIFY_CACHE_REDIS_URL`
- `TESTCODE_DIFY_CACHE_REDIS_PREFIX`
- `TESTCODE_N8N_BASE_URL`
- `TESTCODE_N8N_TIMEOUT_SECONDS`

## Quick start

1. Prepare a settings file, for example `config/settings.example.yaml`.
2. Export secrets or configure environment variables.
3. Run the health check:

```bash
python -m testcode health --settings config/settings.example.yaml
```

4. Run the test flow:

```bash
python -m testcode run-test-flow \
  --settings config/settings.example.yaml \
  --requirement "测试登录功能" \
  --n8n-webhook-url https://example.com/webhook \
  --output artifacts/report.json
```

5. Inspect the cache backend:

```bash
python -m testcode cache-health --settings config/settings.example.yaml
```

## CLI commands

- `health` — print the orchestrator health summary
- `cache-health` — inspect the active Dify cache backend
- `run` — run the provider chain demo
- `run-test-flow` — execute the full test generation and automation flow

## Web UI

Run `streamlit run src/testcode/web_ui.py` to open a lightweight dashboard for submitting requirements, running the flow, and viewing reports.

If `streamlit` is not on your PATH, run `powershell -ExecutionPolicy Bypass -File scripts/start_web_ui.ps1` to launch the UI.

The UI now uses a lighter dashboard-style layout with card-style summaries, progress feedback, simple charts, report tabs, a report list/detail pane, recent report browsing, and report download/delete actions.

## Architecture

### Flow

1. `TestRequirement` captures the user testing need.
2. `TestOrchestrator` generates test cases and enrichment data.
3. `WorkflowOrchestrator` and provider clients coordinate downstream workflow execution.
4. `N8nClient` triggers the automation workflow and can poll for completion.
5. The final report is written to JSON and can be archived in `artifacts/`.

For a minimal local n8n setup, see `docs/n8n-local-webhook.md`.

### Provider responsibilities

- **Dify**: generate test cases and summary reports
- **Coze**: enrich test cases with external data or plugin output
- **n8n**: execute automation workflows and collect execution results

## Testing

Run unit tests:

```bash
pytest
```

Run integration tests:

```bash
pytest -m integration
```

Run coverage:

```bash
pytest --cov=testcode --cov-report=term-missing --cov-report=html
```

## Project structure

- `src/` — application code, adapters, orchestration flows, and shared utilities
- `config/` — environment, provider, and workflow configuration files
- `tests/` — unit and integration tests
- `docs/` — architecture notes, diagrams, and implementation references
- `scripts/` — automation and developer utility scripts
- `artifacts/` — generated outputs, exports, and temporary deliverables

## Contributing

See `CONTRIBUTING.md` for guidance on extending the system and adding new test tasks.

## Release

See `RELEASE.md` and `docs/release-checklist.md` for the release process and pre-publish checklist.

## Release checklist

See `docs/release-checklist.md` before publishing a new version or deploying to production.

## Notes

- Redis cache is optional. If Redis is unavailable, the registry falls back to file cache automatically.
- If you see an import error for `RedisDifyCache`, make sure `src/testcode/cache/__init__.py` exports it and that you have re-run `pip install -e .[dev]` in the active interpreter.
- If you see an `N8nClient` attribute error, re-run the program after updating `src/testcode/adapters/n8n.py` and make sure PyCharm is using the same interpreter where the latest code is installed.
- Keep secrets out of source control.
- Use `artifacts/` for generated reports and outputs that should not be committed.
