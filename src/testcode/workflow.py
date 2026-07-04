from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import logging

from testcode.models.provider_result import ProviderResult
from testcode.providers.registry import ProviderRegistry


@dataclass(slots=True)
class WorkflowOrchestrator:
    registry: ProviderRegistry
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("testcode.workflow"))

    def run_coze_then_dify(
        self,
        *,
        coze_bot_id: str,
        coze_user_id: str,
        coze_query: str,
        dify_user: str,
        dify_inputs: dict[str, Any] | None = None,
        coze_additional_params: dict[str, Any] | None = None,
    ) -> dict[str, ProviderResult]:
        coze = self.registry.get("coze")
        dify = self.registry.get("dify")

        self.logger.info("starting workflow chain", extra={"stage": "coze", "provider": "coze"})
        coze_result = coze.chat(
            bot_id=coze_bot_id,
            user_id=coze_user_id,
            query=coze_query,
            additional_params=coze_additional_params,
        )
        self.logger.info("coze completed", extra={"provider": "coze", "status": "success"})

        merged_inputs = dict(dify_inputs or {})
        merged_inputs.update(
            {
                "coze_content": coze_result.content,
                "coze_raw": coze_result.raw,
                "coze_messages": [
                    {"role": message.role, "content": message.content, "raw": message.raw}
                    for message in coze_result.messages
                ],
            }
        )

        self.logger.info("starting dify step", extra={"stage": "dify", "provider": "dify"})
        dify_result = dify.chat(query=coze_result.content, user=dify_user, inputs=merged_inputs)
        self.logger.info("dify completed", extra={"provider": "dify", "status": "success"})

        return {"coze": coze_result, "dify": dify_result}

    def run_coze_dify_then_n8n(
        self,
        *,
        coze_bot_id: str,
        coze_user_id: str,
        coze_query: str,
        dify_user: str,
        n8n_webhook_url: str,
        dify_inputs: dict[str, Any] | None = None,
        coze_additional_params: dict[str, Any] | None = None,
        n8n_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chain = self.run_coze_then_dify(
            coze_bot_id=coze_bot_id,
            coze_user_id=coze_user_id,
            coze_query=coze_query,
            dify_user=dify_user,
            dify_inputs=dify_inputs,
            coze_additional_params=coze_additional_params,
        )
        n8n = self.registry.get("n8n")
        dify_result = chain["dify"]
        payload = self._build_n8n_payload(dify_result, n8n_payload or {})
        self.logger.info("triggering n8n", extra={"provider": "n8n", "webhook_url": n8n_webhook_url})
        n8n_result = n8n.trigger_workflow(n8n_webhook_url, payload)
        if n8n_result.status.lower() in {"failed", "error", "canceled", "cancelled"}:
            self.logger.error("n8n workflow failed", extra={"provider": "n8n", "status": n8n_result.status})
        else:
            self.logger.info("n8n workflow triggered", extra={"provider": "n8n", "status": n8n_result.status})
        return {"coze": chain["coze"], "dify": dify_result, "n8n": n8n_result}

    def _build_n8n_payload(self, result: ProviderResult, original_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_provider": result.provider,
            "kind": result.kind,
            "content": result.content,
            "messages": [
                {"role": message.role, "content": message.content, "raw": message.raw}
                for message in result.messages
            ],
            "usage": result.usage,
            "raw": result.raw,
            "original_payload": original_payload,
        }
