from __future__ import annotations

from testcode.models import AutomationPayload, TestCase, TestCaseBundle, TestRequirement, TestStep


def test_test_requirement_and_case_models_validate() -> None:
    requirement = TestRequirement(request_id="req-1", requirement="测试登录功能")
    case = TestCase(
        case_id="case-1",
        title="登录成功",
        steps=[TestStep(step_no=1, action="输入账号", expected_result="账号已输入")],
    )

    assert requirement.requirement == "测试登录功能"
    assert case.steps[0].action == "输入账号"


def test_test_case_bundle_holds_cases() -> None:
    bundle = TestCaseBundle(request_id="req-1", cases=[TestCase(case_id="case-1", title="登录成功")])

    assert bundle.cases[0].title == "登录成功"


def test_automation_payload_can_be_constructed() -> None:
    payload = AutomationPayload(
        request_id="req-1",
        suite_name="login_suite",
        cases=[TestCase(case_id="case-1", title="登录成功")],
    )

    assert payload.execution_mode == "playwright"
