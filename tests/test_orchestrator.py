from testcode import Orchestrator


def test_health_check_returns_expected_status() -> None:
    result = Orchestrator().health_check()

    assert result["status"] == "ok"
    assert result["stack"] == "python"
    assert result["providers"] == "n8n,dify,coze"
