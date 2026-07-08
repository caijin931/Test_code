"""Streamlit web UI for Testcode — visual operations for functional, API, and performance testing."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import time

import plotly.graph_objects as go
import streamlit as st

from testcode.adapters.n8n import N8nAPIError
from testcode.api_test_orchestrator import ApiTestOrchestrator
from testcode.app import build_orchestrator
from testcode.models import TestRequirement
from testcode.models.api_test import ApiEndpoint, ApiTestSuite, HttpMethod
from testcode.models.perf_test import LoadPattern, PerformanceProfile
from testcode.models.test_flow import (
    CozeEnrichment,
    ExecutionResult,
    TestCase,
    TestCaseBundle,
    TestStep,
)
from testcode.perf_test_orchestrator import PerfTestOrchestrator
from testcode.test_orchestrator import TestOrchestrator

ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# session state helpers
# ---------------------------------------------------------------------------


def _init_session() -> None:
    """Initialise session_state keys used across tabs."""
    defaults = {
        # API testing wizard state
        "api_step": 1,
        "api_endpoints": [],
        "api_last_result": None,
        "api_config": {"suite_name": "API Test Suite", "base_url": "https://httpbin.org", "description": ""},
        "api_pipeline_status": {"coze": "pending", "generation_done": "pending"},
        "api_error_messages": [],
        # Perf testing wizard state
        "perf_step": 1,
        "perf_last_result": None,
        "perf_profile": None,
        "perf_running": False,
        "perf_config": {"target_url": "https://httpbin.org/get", "profile_name": "Load Test", "description": ""},
        "perf_pipeline_status": {"dify": "pending", "generation_done": "pending"},
        "perf_error_messages": [],
        "perf_editable": {},
        # functional testing wizard state
        "func_step": 1,
        "func_requirement": None,
        "func_requirement_text": "",
        "func_test_cases": None,
        "func_enrichment": None,
        "func_last_result": None,
        "func_pipeline_status": {"dify": "pending", "coze": "pending", "generation_done": "pending"},
        "func_n8n_url": "http://localhost:5678/webhook/testcode/webhook",
        "func_config": {"product_name": "", "module_name": "", "test_type": "ui", "tags": ""},
        "func_error_messages": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ---------------------------------------------------------------------------
# style
# ---------------------------------------------------------------------------


def _inject_style() -> None:
    st.markdown(
        """
        <style>
            .stApp { background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%); }
            .block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1380px; }
            div[data-testid="stMetric"] { background: white; border: 1px solid rgba(49,51,63,0.10); padding: 1rem; border-radius: 1rem; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04); }
            div[data-testid="stTabs"] { background: white; border-radius: 1rem; padding: 0.25rem; border: 1px solid rgba(49,51,63,0.08); }
            section[data-testid="stSidebar"] { background: #fdfefe; border-right: 1px solid rgba(49,51,63,0.08); }
            div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea { border-radius: 0.8rem; }
            .testcode-card { padding: 1rem; border-radius: 1rem; border: 1px solid rgba(49,51,63,0.10); background: rgba(255,255,255,0.92); box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04); }
            .testcode-title { font-size: 0.88rem; color: #64748b; margin-bottom: 0.35rem; }
            .testcode-value { font-size: 1.45rem; font-weight: 800; color: #0f172a; line-height: 1.2; }
            .testcode-help { font-size: 0.8rem; color: #94a3b8; margin-top: 0.35rem; }
            .report-row { display: flex; justify-content: space-between; align-items: center; gap: 1rem; padding: 0.85rem 1rem; border-radius: 0.9rem; border: 1px solid rgba(148,163,184,0.22); background: white; margin-bottom: 0.6rem; }
            .report-row strong { color: #0f172a; }
            .report-row span { color: #64748b; font-size: 0.88rem; }
            .method-badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.75rem; font-weight: 700; color: white; margin-right: 0.5rem; }
            .method-GET { background: #22c55e; }
            .method-POST { background: #3b82f6; }
            .method-PUT { background: #f59e0b; }
            .method-PATCH { background: #8b5cf6; }
            .method-DELETE { background: #ef4444; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _card(title: str, value: str, help_text: str | None = None) -> None:
    st.markdown(
        f"""
        <div class="testcode-card">
            <div class="testcode-title">{title}</div>
            <div class="testcode-value">{value}</div>
            <div class="testcode-help">{help_text or ''}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# functional testing tab (preserved from original)
# ---------------------------------------------------------------------------


def _render_functional_tab(settings_path: Path) -> None:
    """Render the functional testing tab as a 3-step AI-assisted wizard."""
    step = st.session_state.get("func_step", 1)
    _render_step_indicator(step)

    if step == 1:
        _render_func_step1_input(settings_path)
    elif step == 2:
        _render_func_step2_generation(settings_path)
    elif step == 3:
        _render_func_step3_execution(settings_path)


# ---------------------------------------------------------------------------
# step indicator
# ---------------------------------------------------------------------------


def _render_step_indicator(current_step: int) -> None:
    """Render a horizontal 3-step progress indicator."""
    steps = [
        (1, "📝 输入需求"),
        (2, "🤖 AI 生成测试用例"),
        (3, "▶️ 执行与报告"),
    ]

    cols = st.columns(len(steps))
    for idx, (step_num, label) in enumerate(steps):
        with cols[idx]:
            if step_num < current_step:
                icon, bg = "✅", "#22c55e"
            elif step_num == current_step:
                icon, bg = "🔵", "#3b82f6"
            else:
                icon, bg = "⚪", "#e2e8f0"

            st.markdown(
                f"<div style='text-align:center;padding:0.5rem;border-radius:0.75rem;"
                f"background:{bg}20;border:2px solid {bg}'>"
                f"<span style='font-size:1.2rem'>{icon}</span><br/>"
                f"<strong style='color:{bg}'>{label}</strong>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")


# ---------------------------------------------------------------------------
# step 1: input form
# ---------------------------------------------------------------------------


def _render_func_step1_input(settings_path: Path) -> None:
    """Step 1: Input test requirements in a two-column layout."""
    col_left, col_right = st.columns([0.4, 0.6])
    config = st.session_state.func_config

    with col_left:
        st.markdown("### 📝 测试需求配置")

        with st.form("func_input_form"):
            config["product_name"] = st.text_input(
                "产品名称", value=config.get("product_name", ""), placeholder="例如: 电商平台"
            )
            config["module_name"] = st.text_input(
                "模块名称", value=config.get("module_name", ""), placeholder="例如: 用户登录"
            )
            requirement_text = st.text_area(
                "测试需求描述",
                value=st.session_state.get("func_requirement_text", ""),
                height=150,
                placeholder="请详细描述你要测试的功能场景...\n\n例如：验证用户使用邮箱和密码登录，输入正确凭据后成功跳转到首页，输入错误凭据时显示错误提示。",
                key="func_req_input",
            )
            config["test_type"] = st.selectbox(
                "测试类型",
                options=["ui", "api", "integration", "e2e"],
                index=["ui", "api", "integration", "e2e"].index(config.get("test_type", "ui")),
            )
            config["tags"] = st.text_input(
                "标签 (逗号分隔)", value=config.get("tags", ""), placeholder="smoke, regression"
            )

            st.markdown("---")
            n8n_url = st.text_input(
                "n8n Webhook URL",
                value=st.session_state.func_n8n_url,
                placeholder="http://localhost:5678/webhook/testcode/webhook",
                key="func_n8n_input",
            )

            st.markdown("---")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                submitted = st.form_submit_button("🚀 生成测试用例", type="primary", use_container_width=True)
            with col_b2:
                load_last = st.form_submit_button("📂 加载上次结果", use_container_width=True)

    with col_right:
        st.markdown("### 🤖 AI 能力预览")
        _card("Dify", "测试用例生成", "基于需求描述生成结构化测试用例")
        _card("Coze", "测试数据增强", "智能填充测试数据和浏览器配置")
        _card("n8n", "自动化执行", "触发 Playwright 自动化测试工作流")

        st.markdown("---")
        st.markdown("### 📋 输入预览")
        preview_text = requirement_text or "(尚未输入测试需求)"
        product_label = config.get("product_name") or "未指定"
        module_label = config.get("module_name") or "未指定"
        st.info(
            f"**产品**: {product_label}  |  **模块**: {module_label}  |  **类型**: {config.get('test_type', 'ui')}"
        )
        st.markdown(f"> {preview_text[:200]}{'...' if len(preview_text) > 200 else ''}")

    if submitted:
        if not requirement_text.strip():
            st.error("请输入测试需求描述")
        elif not n8n_url.strip():
            st.error("请输入 n8n Webhook URL")
        else:
            tags_list = [t.strip() for t in config.get("tags", "").split(",") if t.strip()]
            requirement = TestRequirement(
                request_id=f"func-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
                requirement=requirement_text.strip(),
                product_name=config["product_name"] or None,
                module_name=config["module_name"] or None,
                test_type=config["test_type"],
                tags=tags_list,
            )
            st.session_state.func_requirement = _jsonable(requirement)
            st.session_state.func_requirement_text = requirement_text
            st.session_state.func_n8n_url = n8n_url
            st.session_state.func_test_cases = None
            st.session_state.func_enrichment = None
            st.session_state.func_last_result = None
            st.session_state.func_pipeline_status = {
                "dify": "pending", "coze": "pending", "generation_done": "pending",
            }
            st.session_state.func_error_messages = []
            st.session_state.func_step = 2
            st.rerun()

    if load_last and st.session_state.func_last_result:
        st.session_state.func_step = 3
        st.rerun()
    elif load_last:
        st.warning("没有找到上次的测试结果")


# ---------------------------------------------------------------------------
# step 2: AI generation + editable review
# ---------------------------------------------------------------------------


def _render_func_step2_generation(settings_path: Path) -> None:
    """Step 2: AI generation pipeline + editable test case review."""
    requirement_data = st.session_state.func_requirement
    if not requirement_data:
        st.error("请先输入测试需求")
        if st.button("⬅️ 返回输入"):
            st.session_state.func_step = 1
            st.rerun()
        return

    requirement = TestRequirement(**requirement_data)

    # Pipeline visualization
    _render_pipeline_bar(st.session_state.func_pipeline_status)

    # Auto-trigger AI generation if not yet done
    if st.session_state.func_test_cases is None:
        _run_ai_generation_pipeline(settings_path, requirement)

    # Error banner if fallback used
    for msg in st.session_state.func_error_messages:
        st.warning(msg)

    # Editable test cases
    cases: list[dict] = st.session_state.func_test_cases or []
    if not cases:
        st.error("未能生成任何测试用例。请返回上一步调整需求后重试。")
        if st.button("⬅️ 返回输入"):
            st.session_state.func_step = 1
            st.rerun()
        return

    st.markdown(f"### 📋 测试用例 ({len(cases)} 个) — 请审核并编辑")
    st.caption("你可以修改任何字段、增删步骤或添加/删除用例。审核完毕后点击「执行测试」。")

    for i in range(len(cases)):
        _render_editable_test_case(i, cases)

    # Add new case
    st.markdown("---")
    if st.button("➕ 添加测试用例", type="secondary"):
        new_case = {
            "case_id": f"TC-{len(cases) + 1:03d}",
            "title": "新测试用例",
            "priority": "medium",
            "severity": "normal",
            "preconditions": [],
            "steps": [],
            "tags": [],
            "_reviewed": False,
        }
        cases.append(new_case)
        st.rerun()

    # Action buttons
    st.markdown("---")
    col_exec, col_regen, col_back = st.columns([2, 1, 1])
    with col_exec:
        exec_btn = st.button("▶️ 执行测试", type="primary", use_container_width=True)
    with col_regen:
        regen_btn = st.button("🔄 重新生成", use_container_width=True)
    with col_back:
        back_btn = st.button("⬅️ 返回修改需求", use_container_width=True)

    if exec_btn:
        if not cases:
            st.error("至少需要一个测试用例")
        else:
            test_case_objects = _dicts_to_test_cases(cases, requirement.request_id)
            st.session_state.func_test_cases = [_jsonable(tc) for tc in test_case_objects]
            st.session_state.func_step = 3
            st.rerun()

    if regen_btn:
        st.session_state.func_test_cases = None
        st.session_state.func_enrichment = None
        st.session_state.func_pipeline_status = {
            "dify": "pending", "coze": "pending", "generation_done": "pending",
        }
        st.session_state.func_error_messages = []
        st.rerun()

    if back_btn:
        st.session_state.func_step = 1
        st.rerun()


# ---------------------------------------------------------------------------
# pipeline bar
# ---------------------------------------------------------------------------


def _render_pipeline_bar(status: dict) -> None:
    """Render the AI pipeline progress visualization."""
    stages = [
        ("dify", "Dify 生成", "AI 生成测试用例"),
        ("coze", "Coze 增强", "智能填充测试数据"),
        ("generation_done", "生成完成", "测试用例已就绪"),
    ]

    cols = st.columns(len(stages))
    status_icons = {
        "pending": ("⚪", "#94a3b8"),
        "running": ("🔄", "#3b82f6"),
        "done": ("✅", "#22c55e"),
        "error": ("⚠️", "#f59e0b"),
    }

    for idx, (key, title, desc) in enumerate(stages):
        with cols[idx]:
            state = status.get(key, "pending")
            icon, color = status_icons.get(state, status_icons["pending"])
            st.markdown(
                f"<div style='text-align:center;padding:0.6rem;border-radius:0.75rem;"
                f"border:2px solid {color}30;background:{color}10'>"
                f"<span style='font-size:1.5rem'>{icon}</span><br/>"
                f"<strong style='color:{color};font-size:0.9rem'>{title}</strong><br/>"
                f"<small style='color:#64748b'>{desc}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )

        if idx < len(stages) - 1:
            st.markdown(
                "<div style='text-align:center;padding-top:1.5rem;color:#94a3b8;font-size:1.2rem'>→</div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")


# ---------------------------------------------------------------------------
# AI generation runner
# ---------------------------------------------------------------------------


def _run_ai_generation_pipeline(settings_path: Path, requirement: TestRequirement) -> None:
    """Execute the AI generation pipeline, updating session state."""
    status = st.session_state.func_pipeline_status
    errors: list[str] = st.session_state.func_error_messages

    try:
        orchestrator = build_orchestrator(settings_path)
    except Exception as exc:
        st.error(f"无法初始化编排器: {exc}")
        st.session_state.func_step = 1
        st.rerun()
        return

    flow = TestOrchestrator(registry=orchestrator.registry)
    dify = orchestrator.registry.get("dify")
    coze = orchestrator.registry.get("coze")

    # Stage 1: Dify generation
    status["dify"] = "running"
    with st.spinner("Dify 正在生成测试用例..."):
        try:
            bundle = flow.generate_test_cases(dify, requirement)
            cases_dicts = [_test_case_to_editable_dict(tc) for tc in bundle.cases]
            st.session_state.func_test_cases = cases_dicts
            status["dify"] = "done"
            if bundle.raw.get("generated_by") == "fallback":
                errors.append(f"Dify 生成失败，已使用模板生成: {bundle.raw.get('error', '未知错误')}")
                status["dify"] = "error"
        except Exception as exc:
            status["dify"] = "error"
            errors.append(f"Dify 生成失败: {exc}")
            bundle = flow._generate_template_cases(requirement, error=str(exc))
            st.session_state.func_test_cases = [
                _test_case_to_editable_dict(tc) for tc in bundle.cases
            ]

    # Stage 2: Coze enrichment
    status["coze"] = "running"
    with st.spinner("Coze 正在增强测试数据..."):
        try:
            enrichment = flow.enrich_test_cases_with_coze(coze, requirement, bundle)
            st.session_state.func_enrichment = _jsonable(enrichment)
            status["coze"] = "done"
            if enrichment.raw.get("generated_by") == "fallback":
                errors.append(f"Coze 增强失败，已使用默认数据: {enrichment.raw.get('error', '未知错误')}")
                status["coze"] = "error"
        except Exception as exc:
            status["coze"] = "error"
            errors.append(f"Coze 增强失败: {exc}")
            fallback = CozeEnrichment(
                request_id=requirement.request_id,
                datasource="coze-fallback",
                test_data={"account": "demo-user", "password": "demo-pass"},
                browser_hints={"browser": "chromium", "headless": True},
                raw={"source": "coze", "generated_by": "fallback", "error": str(exc)},
            )
            st.session_state.func_enrichment = _jsonable(fallback)

    status["generation_done"] = "done"


# ---------------------------------------------------------------------------
# editable test case card
# ---------------------------------------------------------------------------


def _render_editable_test_case(index: int, cases: list[dict]) -> None:
    """Render a single editable test case expander card."""
    case = cases[index]
    reviewed = case.get("_reviewed", False)
    icon = "✅" if reviewed else "📝"

    with st.expander(
        f"{icon} {case.get('title', '未命名用例')} — {case.get('priority', 'medium')} / {case.get('severity', 'normal')}",
        expanded=(index == 0),
    ):
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            case["title"] = st.text_input("用例标题", value=case.get("title", ""), key=f"tc_t_{index}")
        with col2:
            priority_opts = ["high", "medium", "low"]
            current_p = case.get("priority", "medium")
            p_idx = priority_opts.index(current_p) if current_p in priority_opts else 1
            case["priority"] = st.selectbox("优先级", priority_opts, index=p_idx, key=f"tc_p_{index}")
        with col3:
            sev_opts = ["critical", "normal", "minor"]
            current_s = case.get("severity", "normal")
            s_idx = sev_opts.index(current_s) if current_s in sev_opts else 1
            case["severity"] = st.selectbox("严重程度", sev_opts, index=s_idx, key=f"tc_sv_{index}")

        case["_reviewed"] = st.checkbox("已审核", value=reviewed, key=f"tc_rev_{index}")

        # Preconditions
        precond_text = st.text_area(
            "前置条件 (每行一个)",
            value="\n".join(case.get("preconditions", [])),
            height=80,
            key=f"tc_pre_{index}",
        )
        case["preconditions"] = [p.strip() for p in precond_text.split("\n") if p.strip()]

        # Tags
        tags_text = st.text_input(
            "标签 (逗号分隔)",
            value=", ".join(case.get("tags", [])),
            key=f"tc_tags_{index}",
        )
        case["tags"] = [t.strip() for t in tags_text.split(",") if t.strip()]

        # Steps
        st.markdown("**测试步骤**")
        steps: list[dict] = case.get("steps", [])
        for j in range(len(steps)):
            step = steps[j]
            sc1, sc2, sc3 = st.columns([5, 5, 1])
            with sc1:
                step["action"] = st.text_input(
                    "操作",
                    value=step.get("action", ""),
                    key=f"tc_sa_{index}_{j}",
                    label_visibility="collapsed",
                    placeholder="操作描述",
                )
            with sc2:
                step["expected_result"] = st.text_input(
                    "预期结果",
                    value=step.get("expected_result", ""),
                    key=f"tc_se_{index}_{j}",
                    label_visibility="collapsed",
                    placeholder="预期结果",
                )
            with sc3:
                if st.button("🗑️", key=f"tc_del_s_{index}_{j}", help="删除此步骤"):
                    steps.pop(j)
                    st.rerun()

        if st.button("+ 添加步骤", key=f"tc_add_s_{index}"):
            steps.append({"step_no": len(steps) + 1, "action": "", "expected_result": "", "data": {}})
            st.rerun()

        # Delete case
        if st.button("🗑️ 删除此用例", key=f"tc_del_{index}", type="secondary"):
            cases.pop(index)
            st.rerun()


# ---------------------------------------------------------------------------
# step 3: execution + results
# ---------------------------------------------------------------------------


def _render_func_step3_execution(settings_path: Path) -> None:
    """Step 3: Execute tests via n8n and display results."""
    requirement_data = st.session_state.func_requirement
    test_cases_data = st.session_state.func_test_cases
    enrichment_data = st.session_state.func_enrichment
    n8n_url = st.session_state.func_n8n_url

    if not all([requirement_data, test_cases_data, n8n_url]):
        st.error("缺少必要的测试数据，请返回第一步重新开始。")
        if st.button("⬅️ 返回输入"):
            st.session_state.func_step = 1
            st.rerun()
        return

    requirement = TestRequirement(**requirement_data)
    test_cases = _dicts_to_test_cases(test_cases_data, requirement.request_id)
    bundle = TestCaseBundle(request_id=requirement.request_id, cases=test_cases, raw={})

    if enrichment_data:
        enrichment = CozeEnrichment(**enrichment_data)
    else:
        enrichment = CozeEnrichment(request_id=requirement.request_id)

    # Run or show cached result
    if st.session_state.func_last_result is None:
        pipeline_status = st.session_state.func_pipeline_status
        pipeline_status["n8n"] = "running"

        with st.spinner("正在触发 n8n 自动化工作流..."):
            try:
                orchestrator = build_orchestrator(settings_path)
                flow = TestOrchestrator(registry=orchestrator.registry)

                payload = flow.build_automation_payload(requirement, bundle, enrichment)
                n8n = orchestrator.registry.get("n8n")

                try:
                    n8n_trigger = n8n.trigger_workflow(n8n_url, payload.model_dump())
                    if n8n_trigger.execution_id:
                        st.info(f"n8n 工作流已触发，等待完成... (execution_id: {n8n_trigger.execution_id})")
                        n8n_trigger = n8n.wait_for_completion(n8n_trigger.execution_id)
                    execution_result = flow.normalize_execution_result(requirement, n8n_trigger)
                    execution_state = execution_result.status.lower()
                except N8nAPIError as exc:
                    execution_state = "deferred"
                    execution_result = ExecutionResult(
                        request_id=requirement.request_id,
                        status="deferred",
                        raw={"error": str(exc), "status_code": exc.status_code},
                    )

                report = flow.summarize_report(
                    dify_client=orchestrator.registry.get("dify"),
                    requirement=requirement,
                    execution_result=execution_result,
                )

                result = {
                    "requirement": _jsonable(requirement),
                    "test_cases": _jsonable(bundle),
                    "enrichment": _jsonable(enrichment),
                    "automation_payload": _jsonable(payload),
                    "execution_result": _jsonable(execution_result),
                    "execution_state": execution_state,
                    "report": _jsonable(report),
                }
                st.session_state.func_last_result = result
                pipeline_status["n8n"] = "done" if execution_state == "success" else "error"

                # Save report
                report_path = (
                    ARTIFACTS_DIR
                    / f"ui-report-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
                )
                report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                st.success(f"报告已保存: {report_path.name}")

            except Exception as exc:
                st.error(f"执行失败: {exc}")
                pipeline_status["n8n"] = "error"
                return

    # Display results (from cached or fresh)
    result = st.session_state.func_last_result
    if not result:
        return

    execution = result.get("execution_result", {})
    report = result.get("report", {})
    case_count = len(result.get("test_cases", {}).get("cases", []))
    exec_state = result.get("execution_state", "unknown")

    status_map = {"success": "成功", "deferred": "降级", "failed": "失败"}
    status_label = status_map.get(exec_state, exec_state.upper())

    # Metrics row
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        _card("执行状态", status_label)
    with m2:
        _card("测试用例数", str(case_count))
    with m3:
        _card("风险等级", report.get("risk_level", "N/A").upper())
    with m4:
        _card("报告生成", "已完成", f"execution_id: {execution.get('execution_id', 'N/A')}")

    # Status badge
    _render_status_badge(exec_state)

    # Charts
    _render_summary_charts(result)

    # Report summary
    st.markdown("---")
    st.subheader("报告摘要")
    summary_col, issue_col = st.columns([2, 1])
    with summary_col:
        st.markdown(f"**摘要**: {report.get('summary', 'N/A')}")
        st.markdown("**亮点**")
        for item in report.get("highlights", []):
            st.write(f"- {item}")
    with issue_col:
        st.markdown("**问题 / 风险**")
        issues = report.get("issues", [])
        if issues:
            for item in issues:
                st.write(f"- {item}")
        else:
            st.success("当前无明显问题")

    # Detail tabs
    tab1, tab2, tab3 = st.tabs(["完整结果", "自动化载荷", "报告原文"])
    with tab1:
        st.json(result)
    with tab2:
        st.json(result.get("automation_payload", {}))
    with tab3:
        st.json(report)

    # Navigation
    st.markdown("---")
    col_new, col_back = st.columns(2)
    with col_new:
        if st.button("🆕 新建测试", type="primary", use_container_width=True):
            _reset_func_state()
            st.rerun()
    with col_back:
        if st.button("⬅️ 返回编辑测试用例", use_container_width=True):
            st.session_state.func_step = 2
            st.rerun()


# ---------------------------------------------------------------------------
# functional test helpers
# ---------------------------------------------------------------------------


def _reset_func_state() -> None:
    """Reset all functional testing session state to defaults."""
    st.session_state.func_step = 1
    st.session_state.func_requirement = None
    st.session_state.func_requirement_text = ""
    st.session_state.func_test_cases = None
    st.session_state.func_enrichment = None
    st.session_state.func_last_result = None
    st.session_state.func_pipeline_status = {
        "dify": "pending", "coze": "pending", "generation_done": "pending",
    }
    st.session_state.func_error_messages = []


def _test_case_to_editable_dict(tc: TestCase) -> dict:
    """Convert a TestCase Pydantic model to an editable dict for the UI."""
    return {
        "case_id": tc.case_id,
        "title": tc.title,
        "priority": tc.priority,
        "severity": tc.severity,
        "preconditions": list(tc.preconditions),
        "steps": [
            {
                "step_no": s.step_no,
                "action": s.action,
                "expected_result": s.expected_result,
                "data": dict(s.data),
            }
            for s in tc.steps
        ],
        "tags": list(tc.tags),
        "_reviewed": False,
    }


def _dicts_to_test_cases(cases_data: list[dict], request_id: str) -> list[TestCase]:
    """Convert editable dicts back to TestCase Pydantic models."""
    result: list[TestCase] = []
    for i, cd in enumerate(cases_data):
        result.append(
            TestCase(
                case_id=cd.get("case_id", f"{request_id}-{i + 1:03d}"),
                title=cd.get("title", ""),
                priority=cd.get("priority", "medium"),
                severity=cd.get("severity", "normal"),
                preconditions=cd.get("preconditions", []),
                steps=[
                    TestStep(
                        step_no=s.get("step_no", j + 1),
                        action=s.get("action", ""),
                        expected_result=s.get("expected_result", ""),
                        data=s.get("data", {}),
                    )
                    for j, s in enumerate(cd.get("steps", []))
                ],
                tags=cd.get("tags", []),
            )
        )
    return result


# ---------------------------------------------------------------------------
# summary charts (updated for dict-based access)
# ---------------------------------------------------------------------------


def _render_summary_charts(result: dict) -> None:
    """Render donut chart and key metrics from a serialized result dict."""
    report = result.get("report", {})
    execution = result.get("execution_result", {})
    case_count = len(result.get("test_cases", {}).get("cases", []))

    status_key = (execution.get("status", "unknown") or "unknown").lower()
    donut_source = {"success": 0.0, "deferred": 0.0, "failed": 0.0}
    if status_key in donut_source:
        donut_source[status_key] = 1.0
    else:
        donut_source["failed"] = 1.0

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("执行状态占比")
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=list(donut_source.keys()),
                    values=list(donut_source.values()),
                    hole=0.65,
                    sort=False,
                    marker_colors=["#22c55e", "#f59e0b", "#ef4444"],
                    textinfo="label+percent",
                )
            ]
        )
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with chart_col2:
        st.subheader("关键指标")
        progress_value = 1.0 if status_key == "success" else 0.5 if status_key == "deferred" else 0.2
        st.progress(progress_value)
        st.bar_chart(
            {"metrics": [case_count, 1 if report.get("risk_level", "P3").upper() == "P0" else 0]}
        )

    issues = report.get("issues", [])
    if issues:
        st.warning("发现以下问题：")
        for issue in issues:
            st.write(f"- {issue}")
    else:
        st.success("未发现明显问题")


def _render_status_badge(status: str) -> None:
    status_map = {
        "success": ("成功", "#22c55e"),
        "deferred": ("降级", "#f59e0b"),
        "failed": ("失败", "#ef4444"),
    }
    label, color = status_map.get(status.lower(), (status.upper(), "#64748b"))
    st.markdown(
        f"<div style='padding:0.5rem 0.8rem;border-radius:999px;background:{color};color:white;display:inline-block;font-weight:700;'>当前状态：{label}</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# API testing tab
# ---------------------------------------------------------------------------

_METHOD_COLORS = {
    "GET": "#22c55e", "POST": "#3b82f6", "PUT": "#f59e0b",
    "PATCH": "#8b5cf6", "DELETE": "#ef4444", "HEAD": "#64748b", "OPTIONS": "#94a3b8",
}


def _render_api_test_tab(settings_path: Path) -> None:
    """Render the API / interface testing tab as a 3-step AI-assisted wizard."""
    step = st.session_state.get("api_step", 1)
    _render_step_indicator(step)
    if step == 1:
        _render_api_step1_input(settings_path)
    elif step == 2:
        _render_api_step2_endpoints(settings_path)
    elif step == 3:
        _render_api_step3_execution(settings_path)


# ---------------------------------------------------------------------------
# API step 1: input
# ---------------------------------------------------------------------------


def _render_api_step1_input(settings_path: Path) -> None:
    """Step 1: Input API test requirements."""
    col_left, col_right = st.columns([0.4, 0.6])
    config = st.session_state.api_config

    with col_left:
        st.markdown("### 📝 接口测试配置")
        with st.form("api_input_form"):
            config["suite_name"] = st.text_input("套件名称", value=config.get("suite_name", "API Test Suite"))
            config["base_url"] = st.text_input("Base URL", value=config.get("base_url", "https://httpbin.org"))
            description = st.text_area(
                "接口测试描述",
                value=config.get("description", ""),
                height=150,
                placeholder="描述你需要测试的接口...\n\n例如：测试用户管理 API，包含 GET /users 获取列表、POST /users 创建用户、DELETE /users/{id} 删除用户。期望 GET 返回 200，POST 返回 201。",
                key="api_desc_input",
            )
            st.markdown("---")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                submitted = st.form_submit_button("🚀 生成接口端点", type="primary", use_container_width=True)
            with col_b2:
                load_last = st.form_submit_button("📂 加载上次结果", use_container_width=True)

    with col_right:
        st.markdown("### 🤖 AI 能力预览")
        _card("Coze", "接口规范生成", "根据描述自动生成 API 端点定义")
        _card("断言引擎", "自动验证", "自动验证状态码、响应体、响应头")
        _card("报告生成", "结果汇总", "生成通过/失败统计和响应时间分析")

        st.markdown("---")
        st.markdown("### 📋 输入预览")
        st.info(f"**套件**: {config.get('suite_name', '')}  |  **Base URL**: {config.get('base_url', '')}")
        preview = description or "(尚未输入接口描述)"
        st.markdown(f"> {preview[:200]}{'...' if len(preview) > 200 else ''}")

    if submitted:
        if not description.strip():
            st.error("请输入接口测试描述")
        elif not config["base_url"].strip():
            st.error("请输入 Base URL")
        else:
            config["description"] = description
            st.session_state.api_endpoints = []  # Will be populated by AI or manual add
            st.session_state.api_last_result = None
            st.session_state.api_pipeline_status = {"coze": "pending", "generation_done": "pending"}
            st.session_state.api_error_messages = []
            st.session_state.api_step = 2
            st.rerun()

    if load_last and st.session_state.api_last_result:
        st.session_state.api_step = 3
        st.rerun()
    elif load_last:
        st.warning("没有找到上次的测试结果")


# ---------------------------------------------------------------------------
# API step 2: AI generate + review endpoints
# ---------------------------------------------------------------------------


def _render_api_step2_endpoints(settings_path: Path) -> None:
    """Step 2: AI generation + editable endpoint list."""
    config = st.session_state.api_config
    if not config.get("base_url"):
        st.error("请先输入配置")
        if st.button("⬅️ 返回输入"):
            st.session_state.api_step = 1; st.rerun()
        return

    # Pipeline bar
    status = st.session_state.api_pipeline_status
    _render_pipeline_bar(status)

    # Auto-trigger AI generation if not yet done
    if not st.session_state.api_endpoints and status["coze"] == "pending":
        _run_api_ai_generation(settings_path, config.get("description", ""))

    # Error messages
    for msg in st.session_state.api_error_messages:
        st.warning(msg)

    # Editable endpoint list
    endpoints = st.session_state.api_endpoints
    st.markdown(f"### 📋 接口端点 ({len(endpoints)} 个) — 请审核并编辑")
    st.caption("你可以修改端点属性或手动添加新端点。审核完毕后点击「执行测试」。")

    for idx, ep in enumerate(endpoints):
        _render_editable_endpoint(idx, endpoints)

    # Add endpoint manually
    st.markdown("---")
    col_add, _ = st.columns([1, 3])
    with col_add:
        if st.button("➕ 手动添加端点", type="secondary"):
            new_ep = {
                "endpoint_id": f"ep-{len(endpoints) + 1}",
                "name": "新端点",
                "method": "GET",
                "url": "/",
                "expected_status": 200,
                "headers": {},
                "body": None,
                "query_params": {},
                "assertions": [],
                "_reviewed": False,
            }
            endpoints.append(new_ep)
            st.rerun()

    # Action buttons
    st.markdown("---")
    col_exec, col_regen, col_back = st.columns([2, 1, 1])
    with col_exec:
        if st.button("▶️ 执行接口测试", type="primary", use_container_width=True):
            if not endpoints:
                st.error("至少需要一个端点")
            else:
                st.session_state.api_step = 3
                st.rerun()
    with col_regen:
        if st.button("🔄 重新生成", use_container_width=True):
            st.session_state.api_endpoints = []
            st.session_state.api_pipeline_status = {"coze": "pending", "generation_done": "pending"}
            st.session_state.api_error_messages = []
            st.rerun()
    with col_back:
        if st.button("⬅️ 返回修改需求", use_container_width=True):
            st.session_state.api_step = 1
            st.rerun()


def _run_api_ai_generation(settings_path: Path, description: str) -> None:
    """Use Coze to generate API endpoint specs from a natural language description."""
    status = st.session_state.api_pipeline_status
    errors: list[str] = st.session_state.api_error_messages
    status["coze"] = "running"

    with st.spinner("Coze 正在生成接口端点..."):
        try:
            orchestrator = build_orchestrator(settings_path)
            coze = orchestrator.registry.get("coze")
            bot_id = getattr(coze, "bot_id", "") or "api-gen"
            prompt = (
                "你是一个 API 测试专家。请根据以下接口描述生成 API 测试端点列表。\n\n"
                f"接口描述: {description}\n\n"
                '请以 JSON 数组格式返回，每个端点包含以下字段:\n'
                '  endpoint_id: 唯一标识符\n'
                '  name: 端点名称\n'
                '  method: HTTP方法 (GET/POST/PUT/PATCH/DELETE)\n'
                '  url: 路径 (如 /users)\n'
                '  expected_status: 期望的HTTP状态码\n'
                '  headers: 请求头对象 {}\n'
                '  body: 请求体 (JSON对象或null)\n'
                '  query_params: 查询参数对象 {}\n'
                '  assertions: 断言数组 [{"path": "$.body.xxx", "operator": "equals", "expected": "value"}]\n\n'
                "要求：返回有效的 JSON 数组，不要包含额外的文本或 markdown 代码块标记。"
            )
            result = coze.chat(bot_id=bot_id, user_id="web-ui", query=prompt)

            # Parse response
            content = result.content
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
            if match:
                content = match.group(1).strip()
            data = json.loads(content)
            if isinstance(data, dict):
                data = data.get("endpoints", data.get("data", [data]))
            if not isinstance(data, list):
                data = [data]

            endpoints = []
            for ep in data:
                if isinstance(ep, dict):
                    endpoints.append({
                        "endpoint_id": ep.get("endpoint_id", f"ep-{len(endpoints) + 1}"),
                        "name": ep.get("name", "未命名"),
                        "method": ep.get("method", "GET").upper(),
                        "url": ep.get("url", "/"),
                        "expected_status": ep.get("expected_status", 200),
                        "headers": ep.get("headers", {}),
                        "body": ep.get("body"),
                        "query_params": ep.get("query_params", {}),
                        "assertions": ep.get("assertions", []),
                        "_reviewed": False,
                    })

            if endpoints:
                st.session_state.api_endpoints = endpoints
                status["coze"] = "done"
            else:
                raise ValueError("AI did not return any endpoints")
        except Exception as exc:
            status["coze"] = "error"
            errors.append(f"Coze 生成失败: {exc}。请手动添加端点。")
            # Add a default endpoint as fallback
            st.session_state.api_endpoints = [
                {
                    "endpoint_id": "ep-1", "name": "默认端点", "method": "GET", "url": "/",
                    "expected_status": 200, "headers": {}, "body": None,
                    "query_params": {}, "assertions": [], "_reviewed": False,
                }
            ]

    status["generation_done"] = "done"


def _render_editable_endpoint(index: int, endpoints: list[dict]) -> None:
    """Render a single editable endpoint expander card."""
    ep = endpoints[index]
    reviewed = ep.get("_reviewed", False)
    icon = "✅" if reviewed else "📝"
    color = _METHOD_COLORS.get(ep.get("method", "GET"), "#64748b")

    with st.expander(
        f"{icon} {ep.get('name', '未命名')} — "
        f"<span class='method-badge' style='background:{color}'>{ep.get('method', 'GET')}</span> "
        f"<code>{ep.get('url', '/')}</code> (期望 {ep.get('expected_status', 200)})",
        expanded=(index == 0),
    ):
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            ep["name"] = st.text_input("端点名称", value=ep.get("name", ""), key=f"api_n_{index}")
        with col2:
            methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
            cur_m = ep.get("method", "GET").upper()
            m_idx = methods.index(cur_m) if cur_m in methods else 0
            ep["method"] = st.selectbox("Method", methods, index=m_idx, key=f"api_m_{index}")
        with col3:
            ep["expected_status"] = st.number_input(
                "期望状态码", value=ep.get("expected_status", 200),
                min_value=100, max_value=599, key=f"api_es_{index}"
            )

        ep["url"] = st.text_input("URL 路径", value=ep.get("url", "/"), key=f"api_u_{index}")
        ep["_reviewed"] = st.checkbox("已审核", value=reviewed, key=f"api_rev_{index}")

        # Headers and Body
        c_h, c_b = st.columns(2)
        with c_h:
            headers_str = st.text_area(
                "Headers (JSON)", value=json.dumps(ep.get("headers", {}), ensure_ascii=False, indent=2),
                height=80, key=f"api_h_{index}"
            )
            try:
                ep["headers"] = json.loads(headers_str) if headers_str.strip() else {}
            except json.JSONDecodeError:
                st.error("Headers JSON 格式错误")
        with c_b:
            body_val = ep.get("body")
            body_str = st.text_area(
                "Body (JSON)", value=json.dumps(body_val, ensure_ascii=False, indent=2) if body_val else "",
                height=80, key=f"api_b_{index}"
            )
            try:
                ep["body"] = json.loads(body_str) if body_str.strip() else None
            except json.JSONDecodeError:
                st.error("Body JSON 格式错误")

        # Assertions
        st.markdown("**断言规则**")
        assertions: list[dict] = ep.get("assertions", [])
        for j, a in enumerate(assertions):
            ac1, ac2, ac3, ac4 = st.columns([2, 2, 1.5, 1])
            with ac1:
                a["path"] = st.text_input("路径", value=a.get("path", ""), key=f"api_ap_{index}_{j}", placeholder="$.body.id")
            with ac2:
                ops = ["equals", "contains", "matches_regex", "less_than", "greater_than"]
                cur_o = a.get("operator", "equals")
                o_idx = ops.index(cur_o) if cur_o in ops else 0
                a["operator"] = st.selectbox("操作符", ops, index=o_idx, key=f"api_ao_{index}_{j}")
            with ac3:
                expected_str = json.dumps(a.get("expected"), ensure_ascii=False) if a.get("expected") is not None else ""
                new_expected = st.text_input("期望值", value=expected_str, key=f"api_ae_{index}_{j}")
                try:
                    a["expected"] = json.loads(new_expected) if new_expected else None
                except json.JSONDecodeError:
                    a["expected"] = new_expected
            with ac4:
                if st.button("🗑️", key=f"api_adel_{index}_{j}"):
                    assertions.pop(j)
                    st.rerun()

        if st.button("+ 添加断言", key=f"api_adda_{index}"):
            assertions.append({"path": "$.status_code", "operator": "equals", "expected": 200})
            st.rerun()

        if st.button("🗑️ 删除此端点", key=f"api_del_{index}", type="secondary"):
            endpoints.pop(index)
            st.rerun()


# ---------------------------------------------------------------------------
# API step 3: execution + results
# ---------------------------------------------------------------------------


def _render_api_step3_execution(settings_path: Path) -> None:
    """Step 3: Execute API tests and display results."""
    config = st.session_state.api_config
    endpoints_data = st.session_state.api_endpoints

    if not endpoints_data:
        st.error("没有端点可执行，请返回添加。")
        if st.button("⬅️ 返回编辑端点"):
            st.session_state.api_step = 2; st.rerun()
        return

    # Convert dicts to ApiEndpoint models
    api_endpoints: list[ApiEndpoint] = []
    for ep in endpoints_data:
        method_str = ep.get("method", "GET").upper()
        try:
            method_enum = HttpMethod(method_str)
        except ValueError:
            method_enum = HttpMethod.GET
        api_endpoints.append(ApiEndpoint(
            endpoint_id=ep.get("endpoint_id", ""),
            name=ep.get("name", ""),
            method=method_enum,
            url=ep.get("url", "/"),
            expected_status=ep.get("expected_status", 200),
            headers=ep.get("headers", {}),
            body=ep.get("body"),
            query_params=ep.get("query_params", {}),
            assertions=ep.get("assertions", []),
        ))

    suite = ApiTestSuite(
        request_id="ui-api-test",
        suite_name=config.get("suite_name", "API Test Suite"),
        base_url=config.get("base_url", ""),
        endpoints=api_endpoints,
    )

    # Execute or show cached
    if st.session_state.api_last_result is None:
        with st.spinner("正在执行接口测试..."):
            try:
                orchestrator = build_orchestrator(settings_path)
                api_orch = ApiTestOrchestrator(registry=orchestrator.registry)
                result = api_orch.execute_api_test(suite)
                st.session_state.api_last_result = result

                payload = _jsonable(result)
                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                report_path = ARTIFACTS_DIR / f"api-report-{ts}.json"
                report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                st.success(f"测试完成 — 报告保存至 {report_path.name}")
            except Exception as exc:
                st.error(f"执行失败: {exc}")
                st.session_state.api_last_result = None
                return

    result = st.session_state.api_last_result
    if not result:
        return

    report = result["report"]
    results = result["results"]

    # Metrics
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        _card("总端点", str(report.total_endpoints))
    with m2:
        _card("通过", str(report.passed), "绿色=通过")
    with m3:
        _card("失败", str(report.failed), "红色=失败" if report.failed else "")
    with m4:
        _card("平均耗时", f"{report.avg_response_time_ms:.0f}ms")

    # Charts
    st.subheader("响应时间 (ms)")
    names = [r.endpoint_id for r in results]
    times = [r.response_time_ms for r in results]
    colors = ["#22c55e" if r.passed else "#ef4444" for r in results]
    fig = go.Figure(data=[go.Bar(x=names, y=times, marker_color=colors, text=[f"{t:.0f}ms" for t in times], textposition="outside")])
    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), yaxis_title="ms")
    st.plotly_chart(fig, use_container_width=True)

    pie_col, _ = st.columns([1, 1])
    with pie_col:
        fig2 = go.Figure(data=[go.Pie(labels=["通过", "失败"], values=[report.passed, report.failed], hole=0.5, marker_colors=["#22c55e", "#ef4444"])])
        fig2.update_layout(margin=dict(t=0, b=0, l=0, r=0), showlegend=True)
        st.plotly_chart(fig2, use_container_width=True)

    # Detail results
    st.subheader("详细结果")
    for res in results:
        icon = "✅" if res.passed else "❌"
        with st.expander(f"{icon} {res.method} {res.url} — {res.status_code} ({res.response_time_ms:.0f}ms)"):
            st.write(f"**Status**: {res.status_code}")
            st.write(f"**Passed**: {res.passed}")
            if res.error_message:
                st.error(res.error_message)
            if res.assertions:
                st.write("**断言结果**:")
                for a in res.assertions:
                    status_icon = "✅" if a.passed else "❌"
                    st.write(f"- {status_icon} `{a.path}` {a.operator} `{a.expected}` → `{a.actual}`")
            if res.response_body:
                st.json(res.response_body)

    # Navigation
    st.markdown("---")
    col_new, col_back = st.columns(2)
    with col_new:
        if st.button("🆕 新建测试", type="primary", use_container_width=True, key="api_new"):
            _reset_api_state()
            st.rerun()
    with col_back:
        if st.button("⬅️ 返回编辑端点", use_container_width=True, key="api_back"):
            st.session_state.api_step = 2
            st.session_state.api_last_result = None
            st.rerun()


def _reset_api_state() -> None:
    """Reset API testing state."""
    st.session_state.api_step = 1
    st.session_state.api_endpoints = []
    st.session_state.api_last_result = None
    st.session_state.api_config = {"suite_name": "API Test Suite", "base_url": "https://httpbin.org", "description": ""}
    st.session_state.api_pipeline_status = {"coze": "pending", "generation_done": "pending"}
    st.session_state.api_error_messages = []


# ---------------------------------------------------------------------------
# performance testing tab
# ---------------------------------------------------------------------------


def _render_perf_test_tab(settings_path: Path) -> None:
    """Render the performance testing tab as a 3-step AI-assisted wizard."""
    step = st.session_state.get("perf_step", 1)
    _render_step_indicator(step)
    if step == 1:
        _render_perf_step1_input(settings_path)
    elif step == 2:
        _render_perf_step2_profile(settings_path)
    elif step == 3:
        _render_perf_step3_execution(settings_path)


# ---------------------------------------------------------------------------
# Perf step 1: input
# ---------------------------------------------------------------------------


def _render_perf_step1_input(settings_path: Path) -> None:
    """Step 1: Input performance test requirements."""
    col_left, col_right = st.columns([0.4, 0.6])
    config = st.session_state.perf_config

    with col_left:
        st.markdown("### 📝 性能测试配置")
        with st.form("perf_input_form"):
            config["profile_name"] = st.text_input("场景名称", value=config.get("profile_name", "Load Test"))
            config["target_url"] = st.text_input(
                "目标 URL", value=config.get("target_url", "https://httpbin.org/get"),
                placeholder="https://api.example.com/endpoint"
            )
            description = st.text_area(
                "性能测试场景描述",
                value=config.get("description", ""),
                height=150,
                placeholder="描述你需要测试的性能场景...\n\n例如：模拟 50 个并发用户访问首页接口，持续 120 秒，关注 P95 延迟是否超过 500ms。",
                key="perf_desc_input",
            )
            st.markdown("---")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                submitted = st.form_submit_button("🚀 生成性能配置", type="primary", use_container_width=True)
            with col_b2:
                load_last = st.form_submit_button("📂 加载上次结果", use_container_width=True)

    with col_right:
        st.markdown("### 🤖 AI 能力预览")
        _card("Dify", "性能配置建议", "根据场景描述推荐并发数、持续时间、负载模式")
        _card("负载引擎", "异步压测", "基于 asyncio 的高并发请求引擎")
        _card("实时分析", "秒级指标", "响应时间百分位、吞吐量、错误率实时采集")

        st.markdown("---")
        st.markdown("### 📋 输入预览")
        st.info(f"**场景**: {config.get('profile_name', '')}  |  **目标**: {config.get('target_url', '')}")
        preview = description or "(尚未输入场景描述)"
        st.markdown(f"> {preview[:200]}{'...' if len(preview) > 200 else ''}")

    if submitted:
        if not config["target_url"].strip():
            st.error("请输入目标 URL")
        else:
            config["description"] = description
            st.session_state.perf_last_result = None
            st.session_state.perf_profile = None
            st.session_state.perf_pipeline_status = {"dify": "pending", "generation_done": "pending"}
            st.session_state.perf_error_messages = []
            st.session_state.perf_editable = {}
            st.session_state.perf_step = 2
            st.rerun()

    if load_last and st.session_state.perf_last_result:
        st.session_state.perf_step = 3
        st.rerun()
    elif load_last:
        st.warning("没有找到上次的测试结果")


# ---------------------------------------------------------------------------
# Perf step 2: AI suggest + editable profile
# ---------------------------------------------------------------------------


def _render_perf_step2_profile(settings_path: Path) -> None:
    """Step 2: AI-suggested profile + editable review."""
    config = st.session_state.perf_config
    if not config.get("target_url"):
        st.error("请先输入配置")
        if st.button("⬅️ 返回输入"):
            st.session_state.perf_step = 1; st.rerun()
        return

    # Pipeline bar
    status = st.session_state.perf_pipeline_status
    _render_pipeline_bar(status)

    # Auto-trigger AI suggestion if not yet done
    if not st.session_state.perf_editable and status["dify"] == "pending":
        _run_perf_ai_suggestion(settings_path, config)

    # Error messages
    for msg in st.session_state.perf_error_messages:
        st.warning(msg)

    # Editable profile form
    editable = st.session_state.perf_editable
    if not editable:
        editable = {"concurrency": 10, "duration_seconds": 30, "method": "GET",
                    "load_pattern": "constant", "ramp_up_seconds": 0, "warmup_seconds": 0,
                    "headers": {}, "body": None}
        st.session_state.perf_editable = editable

    st.markdown("### ⚙️ 性能配置 — 请审核并调整")

    col_l, col_r = st.columns(2)
    with col_l:
        method = st.selectbox("HTTP Method", ["GET", "POST", "PUT", "PATCH", "DELETE"],
                              index=["GET","POST","PUT","PATCH","DELETE"].index(editable.get("method", "GET")),
                              key="perf_ed_method")
        editable["method"] = method

        load_pattern = st.selectbox(
            "负载模式",
            options=[p.value for p in LoadPattern],
            index=[p.value for p in LoadPattern].index(editable.get("load_pattern", "constant")),
            key="perf_ed_lp",
        )
        editable["load_pattern"] = load_pattern

        concurrency = st.slider("并发数", min_value=1, max_value=500,
                                value=editable.get("concurrency", 10), key="perf_ed_conc")
        editable["concurrency"] = concurrency

    with col_r:
        duration = st.slider("持续时间 (秒)", min_value=5, max_value=600,
                             value=editable.get("duration_seconds", 30), key="perf_ed_dur")
        editable["duration_seconds"] = duration

        ramp_up = st.slider("爬升时间 (秒)", min_value=0, max_value=duration,
                            value=min(editable.get("ramp_up_seconds", 0), duration),
                            key="perf_ed_ramp")
        editable["ramp_up_seconds"] = ramp_up

        warmup = st.number_input("预热时间 (秒)", value=editable.get("warmup_seconds", 0),
                                 min_value=0, max_value=30, key="perf_ed_warm")
        editable["warmup_seconds"] = warmup

    est_requests = concurrency * duration
    st.caption(f"预计请求数: ~{est_requests} (并发 {concurrency} × {duration}s)")

    with st.expander("高级选项"):
        c_h, c_b = st.columns(2)
        with c_h:
            headers_str = st.text_area(
                "Headers (JSON)",
                value=json.dumps(editable.get("headers", {}), ensure_ascii=False, indent=2),
                height=100, key="perf_ed_h",
            )
            try:
                editable["headers"] = json.loads(headers_str) if headers_str.strip() else {}
            except json.JSONDecodeError:
                st.error("Headers JSON 格式错误")
        with c_b:
            body_val = editable.get("body")
            body_str = st.text_area(
                "Body (JSON)",
                value=json.dumps(body_val, ensure_ascii=False, indent=2) if body_val else "",
                height=100, key="perf_ed_b",
            )
            try:
                editable["body"] = json.loads(body_str) if body_str.strip() else None
            except json.JSONDecodeError:
                st.error("Body JSON 格式错误")

    # Action buttons
    st.markdown("---")
    col_exec, col_regen, col_back = st.columns([2, 1, 1])
    with col_exec:
        if st.button("▶️ 执行性能测试", type="primary", use_container_width=True):
            st.session_state.perf_step = 3
            st.rerun()
    with col_regen:
        if st.button("🔄 重新分析", use_container_width=True):
            st.session_state.perf_editable = {}
            st.session_state.perf_pipeline_status = {"dify": "pending", "generation_done": "pending"}
            st.session_state.perf_error_messages = []
            st.rerun()
    with col_back:
        if st.button("⬅️ 返回修改需求", use_container_width=True):
            st.session_state.perf_step = 1
            st.rerun()


def _run_perf_ai_suggestion(settings_path: Path, config: dict) -> None:
    """Use Dify to suggest a performance test profile from description."""
    status = st.session_state.perf_pipeline_status
    errors: list[str] = st.session_state.perf_error_messages
    status["dify"] = "running"

    with st.spinner("Dify 正在分析性能测试场景..."):
        try:
            orchestrator = build_orchestrator(settings_path)
            dify = orchestrator.registry.get("dify")
            prompt = (
                "你是一个性能测试专家。请根据以下场景描述推荐性能测试配置参数。\n\n"
                f"目标 URL: {config.get('target_url', '')}\n"
                f"场景描述: {config.get('description', '通用性能测试')}\n\n"
                "请以 JSON 格式返回推荐参数：\n"
                '{"concurrency": 50, "duration_seconds": 120, "method": "GET", '
                '"load_pattern": "constant", "ramp_up_seconds": 10, "warmup_seconds": 5, '
                '"headers": {}, "body": null}\n\n'
                "说明：\n"
                "- method: GET/POST/PUT/PATCH/DELETE\n"
                "- load_pattern: constant/ramp_up/spike/soak\n"
                "- concurrency: 推荐并发数(1-500)\n"
                "- duration_seconds: 推荐持续时间(5-600)\n"
                "- ramp_up_seconds: 爬升时间\n"
                "- warmup_seconds: 预热时间\n"
                "只返回 JSON，不要包含额外文本。"
            )
            result = dify.chat(query=prompt, user="web-ui", inputs={})

            content = result.content
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
            if match:
                content = match.group(1).strip()
            data = json.loads(content)
            if isinstance(data, dict):
                st.session_state.perf_editable = {
                    "concurrency": int(data.get("concurrency", 10)),
                    "duration_seconds": int(data.get("duration_seconds", 30)),
                    "method": data.get("method", "GET").upper(),
                    "load_pattern": data.get("load_pattern", "constant"),
                    "ramp_up_seconds": int(data.get("ramp_up_seconds", 0)),
                    "warmup_seconds": int(data.get("warmup_seconds", 0)),
                    "headers": data.get("headers", {}),
                    "body": data.get("body"),
                }
            status["dify"] = "done"
        except Exception as exc:
            status["dify"] = "error"
            errors.append(f"Dify 分析失败: {exc}。已使用默认配置。")
            st.session_state.perf_editable = {
                "concurrency": 10, "duration_seconds": 30, "method": "GET",
                "load_pattern": "constant", "ramp_up_seconds": 0, "warmup_seconds": 0,
                "headers": {}, "body": None,
            }

    status["generation_done"] = "done"


# ---------------------------------------------------------------------------
# Perf step 3: execution + results
# ---------------------------------------------------------------------------


def _render_perf_step3_execution(settings_path: Path) -> None:
    """Step 3: Execute performance test and display results."""
    config = st.session_state.perf_config
    editable = st.session_state.perf_editable

    if not config.get("target_url") or not editable:
        st.error("缺少配置，请返回第一步重新开始。")
        if st.button("⬅️ 返回输入"):
            st.session_state.perf_step = 1; st.rerun()
        return

    # Build profile from editable dict
    try:
        pattern = LoadPattern(editable.get("load_pattern", "constant"))
    except ValueError:
        pattern = LoadPattern.CONSTANT

    profile = PerformanceProfile(
        request_id="ui-perf-test",
        profile_name=config.get("profile_name", "Load Test"),
        target_url=config["target_url"],
        method=editable.get("method", "GET"),
        headers=editable.get("headers", {}),
        body=editable.get("body"),
        load_pattern=pattern,
        concurrency=editable.get("concurrency", 10),
        duration_seconds=editable.get("duration_seconds", 30),
        ramp_up_seconds=editable.get("ramp_up_seconds", 0),
        warmup_seconds=editable.get("warmup_seconds", 0),
    )
    st.session_state.perf_profile = profile

    concurrency = profile.concurrency
    duration = profile.duration_seconds

    # Execute or show cached
    if st.session_state.perf_last_result is None:
        st.session_state.perf_running = True
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            orchestrator = build_orchestrator(settings_path)
            perf_orch = PerfTestOrchestrator(registry=orchestrator.registry)

            status_text.info(f"正在执行性能测试... (并发: {concurrency}, 时长: {duration}s)")
            start_time = time.time()

            result = perf_orch.execute_perf_test(profile)
            st.session_state.perf_last_result = result

            elapsed = time.time() - start_time
            progress_bar.progress(1.0)
            status_text.success(f"测试完成 — 耗时 {elapsed:.1f}s")

            # Save report
            payload = _jsonable(result)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            report_path = ARTIFACTS_DIR / f"perf-report-{ts}.json"
            report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            st.success(f"报告已保存: {report_path.name}")

        except Exception as exc:
            progress_bar.progress(1.0)
            status_text.error(f"性能测试失败: {exc}")
            return

    # Display results
    result = st.session_state.perf_last_result
    if not result:
        return

    perf_result = result["result"]
    report = result["report"]
    agg = perf_result.aggregate

    # Metric cards
    if agg:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            _card("总请求数", str(perf_result.total_requests))
        with c2:
            _card("错误率", f"{perf_result.error_rate:.2%}", f"{perf_result.total_errors} errors")
        with c3:
            _card("平均延迟", f"{agg.response_time_avg_ms:.0f}ms")
        with c4:
            _card("P95 延迟", f"{agg.response_time_p95_ms:.0f}ms")

    # Charts
    if perf_result.snapshots:
        snapshots = perf_result.snapshots
        timestamps = [s.timestamp_seconds for s in snapshots]

        st.subheader("响应时间趋势")
        fig_rt = go.Figure()
        fig_rt.add_trace(go.Scatter(x=timestamps, y=[s.response_time_avg_ms for s in snapshots], mode="lines", name="Avg"))
        fig_rt.add_trace(go.Scatter(x=timestamps, y=[s.response_time_p50_ms for s in snapshots], mode="lines", name="P50"))
        fig_rt.add_trace(go.Scatter(x=timestamps, y=[s.response_time_p95_ms for s in snapshots], mode="lines", name="P95"))
        fig_rt.add_trace(go.Scatter(x=timestamps, y=[s.response_time_p99_ms for s in snapshots], mode="lines", name="P99"))
        fig_rt.update_layout(margin=dict(t=0, b=0, l=0, r=0), yaxis_title="ms", xaxis_title="seconds", hovermode="x unified")
        st.plotly_chart(fig_rt, use_container_width=True)

        st.subheader("吞吐量 (RPS)")
        fig_tp = go.Figure()
        fig_tp.add_trace(go.Bar(x=timestamps, y=[s.throughput_rps for s in snapshots], marker_color="#3b82f6", name="RPS"))
        fig_tp.update_layout(margin=dict(t=0, b=0, l=0, r=0), yaxis_title="req/s", xaxis_title="seconds")
        st.plotly_chart(fig_tp, use_container_width=True)

        if any(s.errors_count > 0 for s in snapshots):
            st.subheader("错误数")
            fig_err = go.Figure()
            fig_err.add_trace(go.Bar(x=timestamps, y=[s.errors_count for s in snapshots], marker_color="#ef4444", name="Errors"))
            fig_err.update_layout(margin=dict(t=0, b=0, l=0, r=0), yaxis_title="errors")
            st.plotly_chart(fig_err, use_container_width=True)

    # Analysis report
    st.subheader("分析报告")
    st.markdown(f"**摘要**: {report.summary}")
    st.markdown(f"**风险等级**: {report.risk_level.upper()}")

    if report.highlights:
        st.markdown("**亮点**")
        for h in report.highlights:
            st.write(f"- {h}")
    if report.bottlenecks:
        st.warning("**瓶颈**")
        for b in report.bottlenecks:
            st.write(f"- {b}")
    if report.recommendations:
        st.info("**建议**")
        for r in report.recommendations:
            st.write(f"- {r}")

    # Navigation
    st.markdown("---")
    col_new, col_back = st.columns(2)
    with col_new:
        if st.button("🆕 新建测试", type="primary", use_container_width=True, key="perf_new"):
            _reset_perf_state()
            st.rerun()
    with col_back:
        if st.button("⬅️ 返回调整配置", use_container_width=True, key="perf_back"):
            st.session_state.perf_step = 2
            st.session_state.perf_last_result = None
            st.rerun()


def _reset_perf_state() -> None:
    """Reset performance testing state."""
    st.session_state.perf_step = 1
    st.session_state.perf_last_result = None
    st.session_state.perf_profile = None
    st.session_state.perf_running = False
    st.session_state.perf_config = {"target_url": "https://httpbin.org/get", "profile_name": "Load Test", "description": ""}
    st.session_state.perf_pipeline_status = {"dify": "pending", "generation_done": "pending"}
    st.session_state.perf_error_messages = []
    st.session_state.perf_editable = {}


# ---------------------------------------------------------------------------
# reports tab
# ---------------------------------------------------------------------------


def _render_reports_tab() -> None:
    """Render the reports center with filtering, comparison, and export."""
    st.subheader("报告中心")

    reports = _load_recent_reports()

    # filter
    filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 2])
    with filter_col1:
        report_type = st.selectbox("测试类型", options=["全部", "功能测试", "接口测试", "性能测试"], index=0, key="report_filter_type")
    with filter_col2:
        keyword = st.text_input("搜索", value="", key="report_keyword")

    # apply filters
    filtered = reports
    if report_type == "功能测试":
        filtered = [r for r in filtered if r.name.startswith("ui-report-")]
    elif report_type == "接口测试":
        filtered = [r for r in filtered if r.name.startswith("api-report-")]
    elif report_type == "性能测试":
        filtered = [r for r in filtered if r.name.startswith("perf-report-")]

    keyword_lower = keyword.strip().lower()
    if keyword_lower:
        filtered = [r for r in filtered if keyword_lower in r.name.lower()]

    with filter_col3:
        st.caption(f"共 {len(filtered)} 个匹配报告 / 总计 {len(reports)} 个")

    list_col, detail_col = st.columns([1.1, 1.9])

    with list_col:
        st.markdown("### 报告列表")
        selected = _render_report_list(filtered)

    with detail_col:
        st.markdown("### 报告详情")
        if selected and selected.exists():
            _card("当前选中", selected.name, str(selected))
            content = json.loads(selected.read_text(encoding="utf-8"))
            st.json(content)
            _report_actions(selected)
        elif filtered:
            st.info("点击左侧「查看」按钮打开报告详情。")
        else:
            st.info("当前没有匹配的报告文件。")


def _load_recent_reports() -> list[Path]:
    if not ARTIFACTS_DIR.exists():
        return []
    return sorted(ARTIFACTS_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def _render_report_list(reports: list[Path]) -> Path | None:
    selected = None
    for idx, report in enumerate(reports):
        meta = report.stat()

        # type badge
        badge = ""
        if report.name.startswith("ui-report-"):
            badge = "<span style='color:#22c55e'>[功能]</span>"
        elif report.name.startswith("api-report-"):
            badge = "<span style='color:#3b82f6'>[接口]</span>"
        elif report.name.startswith("perf-report-"):
            badge = "<span style='color:#8b5cf6'>[性能]</span>"

        mtime = datetime.fromtimestamp(meta.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

        row_left, row_right = st.columns([4, 1])
        with row_left:
            st.markdown(
                f"<div class='report-row'><div><strong>{badge} {report.name}</strong><br/><span>大小 {meta.st_size:,} bytes | {mtime}</span></div></div>",
                unsafe_allow_html=True,
            )
        with row_right:
            if st.button("查看", key=f"open_{report.name}_{idx}", use_container_width=True):
                selected = report
    return selected


def _report_actions(selected: Path) -> None:
    col1, col2 = st.columns(2)
    with col1:
        with selected.open("rb") as f:
            st.download_button(label="下载报告 JSON", data=f.read(), file_name=selected.name, mime="application/json", use_container_width=True)
    with col2:
        delete_pressed = st.button("删除当前报告", type="secondary", use_container_width=True)
        if delete_pressed:
            if selected.exists():
                selected.unlink()
                st.success(f"已删除报告：{selected.name}")
                st.rerun()
            else:
                st.warning("报告文件已不存在")


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Testcode", layout="wide", initial_sidebar_state="expanded")
    _inject_style()
    _init_session()

    # --- Password gate (only when ACCESS_PASSWORD is configured) ---
    access_password = ""
    try:
        access_password = st.secrets.get("ACCESS_PASSWORD", "")
    except Exception:
        pass
    if access_password:
        if "authenticated" not in st.session_state:
            st.session_state.authenticated = False
        if not st.session_state.authenticated:
            st.title("🔒 Testcode")
            pwd = st.text_input("请输入访问密码", type="password", key="login_pwd")
            if st.button("登录", type="primary"):
                if pwd == access_password:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("密码错误")
            st.stop()

    # --- Load settings: prefer Streamlit Secrets, fall back to YAML file ---
    settings_path = _load_settings_path()
    _map_secrets_to_env()

    st.title("Testcode 可视化控制台")
    st.caption("功能测试 · 接口测试 · 性能测试 — 统一的测试编排与可视化平台")

    # provider health sidebar
    with st.sidebar:
        st.subheader("系统状态")
        try:
            orch = build_orchestrator(settings_path)
            health = orch.health_check()
            prov_list = health.get("providers", "").split(",")
            for p in prov_list:
                st.markdown(f"🟢 {p.strip().upper()}")
        except Exception:
            st.markdown("🔴 配置加载失败")

    # main tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📋 功能测试", "🔌 接口测试", "⚡ 性能测试", "📊 报告中心"])

    with tab1:
        _render_functional_tab(settings_path)
    with tab2:
        _render_api_test_tab(settings_path)
    with tab3:
        _render_perf_test_tab(settings_path)
    with tab4:
        _render_reports_tab()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _load_settings_path() -> Path:
    default = Path("config/settings.example.yaml")
    text = st.sidebar.text_input("Settings file", value=str(default), key="global_settings")
    return Path(text)


def _map_secrets_to_env() -> None:
    """Map Streamlit Cloud Secrets to environment variables.

    Streamlit Secrets are available via st.secrets but NOT automatically
    mapped to os.environ. This function bridges that gap so the existing
    AppSettings.from_env() picks them up.
    """
    import os

    secret_keys = [
        "TESTCODE_COZE_ACCESS_TOKEN",
        "TESTCODE_COZE_BOT_ID",
        "TESTCODE_COZE_BASE_URL",
        "TESTCODE_COZE_TIMEOUT_SECONDS",
        "TESTCODE_DIFY_API_KEY",
        "TESTCODE_DIFY_BASE_URL",
        "TESTCODE_DIFY_TIMEOUT_SECONDS",
        "TESTCODE_N8N_BASE_URL",
        "TESTCODE_N8N_TIMEOUT_SECONDS",
    ]
    try:
        for key in secret_keys:
            if key in st.secrets and key not in os.environ:
                os.environ[key] = str(st.secrets[key])
    except Exception:
        pass  # st.secrets not available locally — that's fine


def _jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    main()
