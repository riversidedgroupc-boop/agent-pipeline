"""Tests for core/config.py"""
from pathlib import Path
import pytest
from core.config import load_config, get_api_key, ConfigLoadError

ROOT = Path(__file__).resolve().parent.parent


def test_load_config_defaults():
    """Load config from pipeline.yaml with default values."""
    c = load_config(ROOT)
    assert c.model.provider == "anthropic"
    assert c.model.model == "claude-sonnet-4-6"
    assert c.model.max_tokens == 8192
    assert c.model.temperature == 0.3
    assert c.retry == 2
    assert c.output_dir == "examples"
    assert c.verbose is False


def test_get_api_key_raises_when_missing():
    """get_api_key raises ConfigLoadError when env var is not set."""
    with pytest.raises(ConfigLoadError):
        get_api_key("nonexistent_provider")


def test_get_api_key_from_env(monkeypatch):
    """get_api_key reads from environment variable."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
    assert get_api_key("anthropic") == "test-key-123"
