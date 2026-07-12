from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import json
import logging
import re

from testcode.adapters.coze import CozeAPIError
from testcode.adapters.dify import DifyAPIError
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
        if not requirement.requirement.strip():
            raise ValueError("requirement must not be empty")
        if not n8n_webhook_url.strip():
            raise ValueError("n8n_webhook_url must not be empty")

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
        execution_state = "success"
        try:
            n8n_trigger = n8n.trigger_workflow(n8n_webhook_url, payload.model_dump())
            if n8n_trigger.execution_id:
                n8n_trigger = n8n.wait_for_completion(n8n_trigger.execution_id)
            execution_result = self.normalize_execution_result(requirement, n8n_trigger)
            execution_state = execution_result.status.lower()
        except N8nAPIError as exc:
            execution_state = "deferred"
            execution_result = ExecutionResult(
                request_id=requirement.request_id,
                execution_id=None,
                status=execution_state,
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
            "execution_state": execution_state,
            "report": report,
        }

    def generate_test_cases(self, dify_client: Any, requirement: TestRequirement) -> TestCaseBundle:
        """Generate test cases via Dify AI, falling back to template on failure."""
        prompt = self._build_test_case_prompt(requirement)
        try:
            self.logger.info("Calling Dify for test case generation", extra={"request_id": requirement.request_id})
            result = dify_client.chat(query=prompt, user="web-ui", inputs={})
            data = self._extract_json_from_response(result.content)
            cases = self._parse_test_cases_from_dict(data, requirement)
            self.logger.info("Dify generated %d test cases", len(cases))
            return TestCaseBundle(
                request_id=requirement.request_id,
                cases=cases,
                raw={"source": "dify", "generated_by": "ai", "provider_raw": result.raw},
            )
        except (DifyAPIError, CozeAPIError, ValueError, ConnectionError, Exception) as exc:
            self.logger.warning("Dify generation failed, falling back to template: %s", exc)
            return self._generate_template_cases(requirement, error=str(exc))

    def enrich_test_cases_with_coze(
        self, coze_client: Any, requirement: TestRequirement, bundle: TestCaseBundle
    ) -> CozeEnrichment:
        """Enrich test cases via Coze AI, falling back to defaults on failure."""
        prompt = self._build_enrichment_prompt(requirement, bundle)
        try:
            self.logger.info("Calling Coze for test case enrichment", extra={"request_id": requirement.request_id})
            bot_id = getattr(coze_client, "bot_id", "") or ""
            result = coze_client.chat(bot_id=bot_id, user_id="web-ui", query=prompt)
            data = self._extract_json_from_response(result.content)
            return CozeEnrichment(
                request_id=requirement.request_id,
                datasource="coze-ai",
                test_data=data.get("test_data", {"account": "demo-user", "password": "demo-pass"}),
                browser_hints=data.get("browser_hints", {"browser": "chromium", "headless": True}),
                raw={
                    "source": "coze",
                    "generated_by": "ai",
                    "case_count": len(bundle.cases),
                    "provider_raw": result.raw,
                },
            )
        except (DifyAPIError, CozeAPIError, ValueError, ConnectionError, Exception) as exc:
            self.logger.warning("Coze enrichment failed, using defaults: %s", exc)
            return CozeEnrichment(
                request_id=requirement.request_id,
                datasource="coze-fallback",
                test_data={"account": "demo-user", "password": "demo-pass"},
                browser_hints={"browser": "chromium", "headless": True},
                raw={
                    "source": "coze",
                    "generated_by": "fallback",
                    "case_count": len(bundle.cases),
                    "error": str(exc),
                    "raw_response_preview": str(getattr(exc, "raw", ""))[:500] if hasattr(exc, "raw") else str(exc)[:500],
                },
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

    def summarize_report(
        self, dify_client: Any, requirement: TestRequirement, execution_result: ExecutionResult
    ) -> TestReport:
        """Generate a test report, attempting AI summary with Dify and falling back to static text."""
        status = execution_result.status.lower()

        # Deterministic highlights and risk from status
        if status == "success":
            issues: list[str] = []
            risk_level = "P3"
            highlights = ["用例已生成", "数据已补充", "自动化已触发", "执行成功"]
        elif status == "deferred":
            issues = ["n8n 不可用，已降级为延后执行"]
            risk_level = "P2"
            highlights = ["用例已生成", "数据已补充", "自动化已触发", "已降级处理"]
        else:
            issues = ["自动化测试存在失败项"]
            risk_level = "P0"
            highlights = ["用例已生成", "数据已补充", "自动化已触发", "需要人工复核"]

        # Try AI summary
        summary = self._build_static_summary(status)
        try:
            prompt = (
                "请根据以下测试执行结果生成一段简洁的中文执行摘要（100字以内）。"
                "只输出摘要文字，不要输出JSON、代码块或任何其他格式。\n"
                f"执行状态: {status}\n"
                f"执行ID: {execution_result.execution_id or 'N/A'}\n"
                f"原始结果: {json.dumps(execution_result.raw, ensure_ascii=False)[:1000]}"
            )
            result = dify_client.chat(query=prompt, user="web-ui", inputs={})
            raw = (result.content or "").strip()
            # Reject responses that look like test-case JSON, model reasoning, or are too long
            if raw and len(raw) > 10 and len(raw) < 500:
                if "{" not in raw and "<think>" not in raw and '"cases"' not in raw:
                    summary = raw
        except Exception as exc:
            self.logger.warning("AI summary generation failed, using static summary: %s", exc)

        return TestReport(
            request_id=requirement.request_id,
            summary=summary,
            risk_level=risk_level,
            highlights=highlights,
            issues=issues,
            raw={"status": execution_result.status, "execution_id": execution_result.execution_id},
        )

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_test_case_prompt(self, requirement: TestRequirement) -> str:
        """Build a Chinese prompt for Dify to generate structured test cases."""
        parts = [
            "你是一个测试用例生成专家。请根据以下测试需求生成结构化的测试用例。",
            f"产品: {requirement.product_name or '未指定'}",
            f"模块: {requirement.module_name or '未指定'}",
            f"测试需求: {requirement.requirement}",
            f"测试类型: {requirement.test_type}",
            "",
            "请生成详细的测试用例，以 JSON 格式返回，格式如下：",
            "{",
            '  "cases": [',
            "    {",
            '      "case_id": "TC-001",',
            '      "title": "用例标题",',
            '      "priority": "high",',
            '      "severity": "critical",',
            '      "preconditions": ["前置条件1", "前置条件2"],',
            '      "steps": [',
            '        {"step_no": 1, "action": "操作描述", "expected_result": "预期结果", "data": {}},',
            '        {"step_no": 2, "action": "操作描述", "expected_result": "预期结果", "data": {}}',
            "      ],",
            '      "tags": ["标签1"]',
            "    }",
            "  ]",
            "}",
            "",
            "要求：",
            "1. 请确保返回的是有效的 JSON，不要包含 markdown 代码块标记以外的额外文本。",
            "2. priority 只能是 high / medium / low",
            "3. severity 只能是 critical / normal / minor",
            "4. 生成至少 1 个，最多 8 个测试用例",
            "5. 每个用例至少包含 2 个测试步骤",
            "6. 步骤中的 data 字段可以为空对象 {}",
        ]
        return "\n".join(parts)

    def _build_enrichment_prompt(self, requirement: TestRequirement, bundle: TestCaseBundle) -> str:
        """Build a Chinese prompt for Coze to enrich test cases with data and browser hints."""
        case_summaries = [
            f"  - {c.case_id}: {c.title} ({c.priority}/{c.severity}, {len(c.steps)} 步)"
            for c in bundle.cases
        ]
        parts = [
            "你是一个测试数据生成专家。请根据以下测试用例生成合适的测试数据和浏览器配置。",
            f"产品: {requirement.product_name or '未指定'}",
            f"模块: {requirement.module_name or '未指定'}",
            f"测试需求: {requirement.requirement}",
            "",
            "测试用例列表：",
            *case_summaries,
            "",
            "请以 JSON 格式返回，包含以下字段：",
            "{",
            '  "test_data": {',
            '    "account": "测试账号",',
            '    "password": "测试密码",',
            '    "url": "测试地址"',
            "    // 根据实际场景补充更多字段",
            "  },",
            '  "browser_hints": {',
            '    "browser": "chromium",',
            '    "headless": true,',
            '    "viewport": {"width": 1920, "height": 1080}',
            "  }",
            "}",
        ]
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # JSON extraction & parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json_from_response(content: str) -> dict[str, Any]:
        """Extract a JSON object from an AI response string.

        Handles: plain JSON, JSON inside ```json blocks, JSON with surrounding
        text, DeepSeek-R1 ``<think>...</think>`` blocks, and common Chinese
        opening phrases like "好的，我将为你回答".
        """
        # Strip <think>...</think> blocks (DeepSeek-R1 reasoning)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # Strip common Chinese / English opening phrases
        content = re.sub(
            r"^(好的[，,]\s*我将为你回答|好的[，,]?\s*|我来回答[：:]?\s*|OK[，,]\s*I will answer[：:]?\s*)",
            "", content, flags=re.IGNORECASE,
        ).strip()

        # Try markdown code block first
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
        else:
            # Try to find first { ... } block
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                candidate = match.group(0).strip()
            else:
                candidate = content.strip()

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # If truncated, try to complete the JSON by counting braces
        try:
            return _complete_truncated_json(candidate)
        except json.JSONDecodeError:
            pass

        # Last resort: try entire content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            raise ValueError(
                f"Failed to parse AI response as JSON. "
                f"Raw content: {content[:300]}"
            )

    def _parse_test_cases_from_dict(
        self, data: dict[str, Any], requirement: TestRequirement
    ) -> list[TestCase]:
        """Parse AI response dict into a list of TestCase objects."""
        raw_cases = data.get("cases", [data] if isinstance(data, dict) else [])
        if isinstance(raw_cases, dict):
            raw_cases = [raw_cases]

        cases: list[TestCase] = []
        for idx, raw in enumerate(raw_cases):
            steps = []
            for step_raw in raw.get("steps", []):
                steps.append(
                    TestStep(
                        step_no=int(step_raw.get("step_no", len(steps) + 1)),
                        action=str(step_raw.get("action", "")),
                        expected_result=str(step_raw.get("expected_result", "")),
                        data=step_raw.get("data", {})
                        if isinstance(step_raw.get("data"), dict)
                        else {},
                    )
                )

            priority = str(raw.get("priority", "medium")).lower()
            if priority not in ("high", "medium", "low"):
                priority = "medium"
            severity = str(raw.get("severity", "normal")).lower()
            if severity not in ("critical", "normal", "minor"):
                severity = "normal"

            cases.append(
                TestCase(
                    case_id=str(raw.get("case_id", f"{requirement.request_id}-{idx + 1:03d}")),
                    title=str(raw.get("title", f"Test Case {idx + 1}")),
                    preconditions=[str(p) for p in raw.get("preconditions", [])],
                    steps=steps,
                    priority=priority,
                    severity=severity,
                    tags=[str(t) for t in raw.get("tags", [])],
                )
            )
        return cases

    def _generate_template_cases(
        self, requirement: TestRequirement, error: str = ""
    ) -> TestCaseBundle:
        """Fallback: generate template-based test cases when AI is unavailable."""
        title = f"{requirement.requirement} - 基础测试(模板)"
        steps = [
            TestStep(
                step_no=1,
                action=f"打开 {requirement.module_name or '目标页面'}",
                expected_result="页面加载成功",
            ),
            TestStep(step_no=2, action="输入合法测试数据", expected_result="字段输入成功"),
            TestStep(step_no=3, action="提交表单", expected_result="操作完成并展示结果"),
        ]
        return TestCaseBundle(
            request_id=requirement.request_id,
            cases=[
                TestCase(
                    case_id=f"{requirement.request_id}-001",
                    title=title,
                    preconditions=["系统可访问", "测试账号可用"],
                    steps=steps,
                    tags=requirement.tags,
                )
            ],
            raw={"source": "template", "generated_by": "fallback", "error": error},
        )

    @staticmethod
    def _build_static_summary(status: str) -> str:
        """Return a static Chinese summary based on execution status."""
        summary_map = {
            "success": "测试流已完成，自动化执行成功。",
            "deferred": "测试流已完成，但自动化执行已降级为延后处理。",
            "failed": "测试流已完成，但自动化执行失败。",
        }
        return summary_map.get(status, f"测试流已完成，状态为 {status}。")


def _complete_truncated_json(text: str) -> dict[str, Any]:
    """Attempt to complete a truncated JSON string by closing unclosed braces/brackets."""
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    suffix = "]" * max(0, open_brackets) + "}" * max(0, open_braces)
    return json.loads(text + suffix)
