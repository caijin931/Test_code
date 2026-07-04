from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import logging

from testcode.adapters.n8n import N8nAPIError
from testcode.models import (
    AutomationPayload,
    CozeEnrichment,
    ExecutionResult,
    TestCase,
    TestCaseBundle,
    TestReport,
    TestRequirement,
    TestStep,
)
from testcode.providers.registry import ProviderRegistry


@dataclass(slots=True)
class TestOrchestrator:
    registry: ProviderRegistry
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("testcode.test_orchestrator"))

    def execute_test_flow(self, requirement: TestRequirement, n8n_webhook_url: str) -> dict[str, Any]:
        dify = self.registry.get("dify")
        coze = self.registry.get("coze")
        n8n = self.registry.get("n8n")

        self.logger.info("test flow start", extra={"request_id": requirement.request_id, "stage": "dify"})
        test_case_bundle = self.generate_test_cases(dify, requirement)
        self.logger.info("test cases generated", extra={"request_id": requirement.request_id, "case_count": len(test_case_bundle.cases)})

        self.logger.info("coze enrichment start", extra={"request_id": requirement.request_id, "stage": "coze"})
        enrichment = self.enrich_test_cases_with_coze(coze, requirement, test_case_bundle)
        self.logger.info("coze enrichment done", extra={"request_id": requirement.request_id})

        payload = self.build_automation_payload(requirement, test_case_bundle, enrichment)
        self.logger.info("n8n trigger start", extra={"request_id": requirement.request_id, "stage": "n8n"})
        try:
            n8n_trigger = n8n.trigger_workflow(n8n_webhook_url, payload.model_dump())
            if n8n_trigger.execution_id:
                n8n_trigger = n8n.wait_for_completion(n8n_trigger.execution_id)
            execution_result = self.normalize_execution_result(requirement, n8n_trigger)
        except N8nAPIError as exc:
            execution_result = ExecutionResult(
                request_id=requirement.request_id,
                execution_id=None,
                status="deferred",
                raw={"error": str(exc), "status_code": exc.status_code, "raw": exc.raw},
            )
            self.logger.warning(
                "n8n unavailable, falling back to deferred execution",
                extra={"request_id": requirement.request_id, "status_code": exc.status_code},
            )
        self.logger.info("n8n execution done", extra={"request_id": requirement.request_id, "status": execution_result.status})

        report = self.summarize_report(dify, requirement, execution_result)
        self.logger.info("report generated", extra={"request_id": requirement.request_id})

        return {
            "requirement": requirement,
            "test_cases": test_case_bundle,
            "enrichment": enrichment,
            "automation_payload": payload,
            "execution_result": execution_result,
            "report": report,
        }

    def generate_test_cases(self, dify_client: Any, requirement: TestRequirement) -> TestCaseBundle:
        title = f"{requirement.requirement} - 基础测试"
        steps = [
            TestStep(step_no=1, action=f"打开 {requirement.module_name or '目标页面'}", expected_result="页面加载成功"),
            TestStep(step_no=2, action="输入合法测试数据", expected_result="字段输入成功"),
            TestStep(step_no=3, action="提交表单", expected_result="操作完成并展示结果"),
        ]
        cases = [
            TestCase(
                case_id=f"{requirement.request_id}-001",
                title=title,
                preconditions=["系统可访问", "测试账号可用"],
                steps=steps,
                tags=requirement.tags,
            )
        ]
        return TestCaseBundle(request_id=requirement.request_id, cases=cases, raw={"source": "dify", "note": "template-generated"})

    def enrich_test_cases_with_coze(self, coze_client: Any, requirement: TestRequirement, bundle: TestCaseBundle) -> CozeEnrichment:
        return CozeEnrichment(
            request_id=requirement.request_id,
            datasource="coze-plugin",
            test_data={"account": "demo-user", "password": "demo-pass"},
            browser_hints={"browser": "chromium", "headless": True},
            raw={"source": "coze", "case_count": len(bundle.cases)},
        )

    def build_automation_payload(self, requirement: TestRequirement, bundle: TestCaseBundle, enrichment: CozeEnrichment) -> AutomationPayload:
        return AutomationPayload(
            request_id=requirement.request_id,
            suite_name=f"{requirement.module_name or 'general'}_suite",
            cases=bundle.cases,
            test_data=enrichment.test_data,
            browser_hints=enrichment.browser_hints,
            env={"product_name": requirement.product_name, "module_name": requirement.module_name},
        )

    def normalize_execution_result(self, requirement: TestRequirement, n8n_result: Any) -> ExecutionResult:
        return ExecutionResult(
            request_id=requirement.request_id,
            execution_id=getattr(n8n_result, "execution_id", None),
            status=getattr(n8n_result, "status", "unknown"),
            raw=getattr(n8n_result, "raw", {}),
        )

    def summarize_report(self, dify_client: Any, requirement: TestRequirement, execution_result: ExecutionResult) -> TestReport:
        summary = f"测试流已完成，状态为 {execution_result.status}。"
        issues = [] if execution_result.status.lower() == "success" else ["自动化测试存在失败项"]
        if execution_result.status == "deferred":
            issues.append("n8n 不可用，已降级为延后执行")
        return TestReport(
            request_id=requirement.request_id,
            summary=summary,
            risk_level="low" if execution_result.status.lower() == "success" else "high",
            highlights=["用例已生成", "数据已补充", "自动化已触发"],
            issues=issues,
            raw={"status": execution_result.status, "execution_id": execution_result.execution_id},
        )
