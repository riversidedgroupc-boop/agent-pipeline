"""Tests for core/runner.py"""
import pytest
from core.runner import RunResult, AgentRunner, UnsupportedProviderError
from core.schema import ModelConfig, PipelineConfig


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


def test_agent_runner_rejects_unsupported_provider():
    """AgentRunner raises UnsupportedProviderError for non-anthropic providers."""
    config = PipelineConfig(
        model=ModelConfig(provider="openai", model="gpt-4o"),
    )
    with pytest.raises(UnsupportedProviderError, match="openai"):
        AgentRunner(config)


def test_agent_runner_accepts_anthropic():
    """AgentRunner accepts anthropic provider (does not require API key at init)."""
    config = PipelineConfig(
        model=ModelConfig(provider="anthropic", model="claude-sonnet-4-6"),
    )
    runner = AgentRunner(config)
    assert runner.config.model.provider == "anthropic"
