"""
Pipeline configuration loader.

Reads pipeline.yaml at project root, merges with environment variables.
API keys are NEVER stored in YAML — they come from env vars only.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from core.schema import ModelConfig, PipelineConfig


class ConfigLoadError(Exception):
    """Raised when required config is missing."""


def _env_or_raise(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise ConfigLoadError(
            f"Environment variable {key} is required. "
            f"Set it or copy .env.example to .env and fill in values."
        )
    return val


def load_config(root: Path) -> PipelineConfig:
    """Load pipeline config from pipeline.yaml, merge env vars for secrets."""
    config_path = root / "pipeline.yaml"

    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    else:
        raw = {}

    model_raw = raw.get("model", {})
    model = ModelConfig(
        provider=model_raw.get("provider", "anthropic"),
        model=model_raw.get("model", "claude-sonnet-4-6"),
        max_tokens=model_raw.get("max_tokens", 8192),
        temperature=model_raw.get("temperature", 0.3),
    )

    return PipelineConfig(
        model=model,
        retry=raw.get("retry", 2),
        output_dir=raw.get("output_dir", "examples"),
        verbose=raw.get("verbose", False),
    )


def get_api_key(provider: str) -> str:
    """Get API key from environment for the given provider."""
    key_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }
    env_var = key_map.get(provider, f"{provider.upper()}_API_KEY")
    return _env_or_raise(env_var)
