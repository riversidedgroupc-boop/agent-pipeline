"""Tests for core/engine.py"""
from pathlib import Path
from core.engine import PipelineEngine, EngineResult


def test_engine_result_empty():
    result = EngineResult(project="test", completed_agents=[], failed_agents=[])
    assert result.all_success is True
    assert len(result.completed_agents) == 0


def test_engine_result_with_failure():
    result = EngineResult(
        project="test",
        completed_agents=["01-pm"],
        failed_agents=["02-mechanical"],
    )
    assert result.all_success is False


def test_engine_has_run_single_and_run_all():
    """Verify engine exposes both independent and batch execution."""
    engine = PipelineEngine(Path("D:/work/agent-pipeline"))
    assert hasattr(engine, "run_single")
    assert hasattr(engine, "run_all")


def test_engine_result_summary():
    result = EngineResult(
        project="pic",
        completed_agents=["01-pm", "02-mechanical"],
        failed_agents=[],
        total_tokens=5000,
        total_duration_ms=12345.6,
    )
    summary = result.summary
    assert "pic" in summary
    assert "2/2" in summary
    assert "5,000" in summary
    assert "12.3s" in summary
