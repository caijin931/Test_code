# Local n8n Webhook Setup

This guide shows the smallest possible setup to test the end-to-end flow locally.

## 1. Start the compose stack

```bash
docker compose up --build
```

This starts:

- `app` — the Testcode CLI
- `redis` — optional cache backend
- `n8n` — local workflow engine

## 2. Open n8n

Visit:

```text
http://localhost:5678
```

## 3. Create a webhook workflow

In n8n:

1. Create a new workflow.
2. Add a `Webhook` trigger node.
3. Set the method to `POST`.
4. Choose a path such as `testcode/webhook`.
5. Add a `Respond to Webhook` node.
6. Return a simple JSON body like:

```json
{
  "status": "success",
  "executionId": "demo-exec-001",
  "data": {
    "passed": 3,
    "failed": 0,
    "report_url": "http://localhost:5678"
  }
}
```

## 4. Copy the webhook URL

Your webhook URL will look similar to:

```text
http://localhost:5678/webhook/testcode/webhook
```

## 5. Run the CLI with the webhook URL

```bash
python -m testcode run-test-flow \
  --settings config/settings.example.yaml \
  --requirement "测试登录功能" \
  --n8n-webhook-url http://localhost:5678/webhook/testcode/webhook \
  --output artifacts/report.json
```

## 6. Expected behavior

- The flow generates test cases.
- The webhook is triggered.
- If the webhook returns JSON, the execution result is captured.
- If the webhook returns plain text or empty content, the client still treats it as a successful ACK.
- If the webhook fails, the orchestrator degrades gracefully and returns a deferred execution result.

## 7. Troubleshooting

- Make sure the webhook node method matches `POST`.
- Confirm the path is correct.
- Check that the `n8n` container is running.
- If you change the workflow, re-test the webhook URL.
