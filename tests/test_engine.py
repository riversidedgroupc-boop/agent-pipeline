"""Tests for core/engine.py"""
from pathlib import Path
import pytest
from core.engine import PipelineEngine, EngineResult

ROOT = Path(__file__).resolve().parent.parent


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
    engine = PipelineEngine(ROOT)
    assert hasattr(engine, "run_single")
    assert hasattr(engine, "run_all")


def test_run_all_rejects_bad_from_agent():
    """run_all raises ValueError when from_agent does not exist."""
    engine = PipelineEngine(ROOT)
    with pytest.raises(ValueError, match="not found"):
        engine.run_all("test", from_agent="99-nonexistent")


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
