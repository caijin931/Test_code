# Deployment Guide

## Docker image

Build the image with:

```bash
docker build -t testcode:latest .
```

## Docker Compose

Start the application and optional Redis cache with:

```bash
docker compose up --build
```

The compose stack includes:

- `app` for the CLI/runtime
- `redis` for Dify caching
- `n8n` for local webhook-driven automation

## n8n webhook expectations

The `N8nClient` triggers workflows by posting to a webhook URL. The workflow should return an execution identifier or a structured result payload so the orchestrator can poll or summarize the outcome.

For a minimal local setup, see `docs/n8n-local-webhook.md`.
## Recommended runtime configuration

Set the following environment variables in production:

- `TESTCODE_COZE_ACCESS_TOKEN`
- `TESTCODE_DIFY_API_KEY`
- `TESTCODE_N8N_BASE_URL`
- `TESTCODE_DIFY_CACHE_BACKEND`
- `TESTCODE_DIFY_CACHE_REDIS_URL`

## Artifact handling

Write generated reports to `artifacts/` and mount that directory as a persistent volume if you want to retain execution outputs across runs.
