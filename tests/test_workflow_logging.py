from __future__ import annotations

import logging

from testcode.models.provider_result import ProviderMessage, ProviderResult
from testcode.workflow import WorkflowOrchestrator


class DummyProvider:
    def __init__(self, result: ProviderResult):
        self.result = result

    def chat(self, *args, **kwargs):
        return self.result


class DummyN8n:
    def trigger_workflow(self, webhook_url, payload):
        return type("R", (), {"status": "failed", "content": "", "execution_id": "e1", "result": payload, "raw": payload})()


class DummyRegistry:
    def __init__(self):
        self.coze = DummyProvider(ProviderResult(provider="coze", kind="chat", content="coze", messages=[ProviderMessage(role="assistant", content="coze")], usage={}, raw={}))
        self.dify = DummyProvider(ProviderResult(provider="dify", kind="chat", content="dify", messages=[ProviderMessage(role="assistant", content="dify")], usage={}, raw={}))
        self.n8n = DummyN8n()

    def get(self, name):
        return getattr(self, name)


def test_workflow_logs_and_marks_failed_n8n(caplog):
    orchestrator = WorkflowOrchestrator(registry=DummyRegistry(), logger=logging.getLogger("testcode.workflow.test"))

    with caplog.at_level(logging.INFO):
        result = orchestrator.run_coze_dify_then_n8n(
            coze_bot_id="b",
            coze_user_id="u",
            coze_query="q",
            dify_user="u",
            n8n_webhook_url="https://example.com/webhook",
        )

    assert result["n8n"].status == "failed"
    assert any("triggering n8n" in rec.message for rec in caplog.records)
