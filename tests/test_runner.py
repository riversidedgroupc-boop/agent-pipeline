"""Tests for core/runner.py"""
from core.runner import RunResult, AgentRunner


def test_run_result_success():
    result = RunResult(
        agent_id="01-pm",
        success=True,
        output="Product spec content",
        tokens_used=1500,
    )
    assert result.success
    assert result.output == "Product spec content"
    assert result.error is None


def test_run_result_failure():
    result = RunResult(
        agent_id="02-mechanical",
        success=False,
        output="",
        error="API key not configured",
    )
    assert not result.success
    assert result.error == "API key not configured"


def test_run_result_defaults():
    result = RunResult(agent_id="test", success=True, output="ok")
    assert result.tokens_used == 0
    assert result.duration_ms == 0.0
    assert result.error is None
