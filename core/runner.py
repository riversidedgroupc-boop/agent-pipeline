"""
Single-agent LLM runner.

Invokes LLM API with assembled prompt context.
Supports Anthropic and DeepSeek providers.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import PipelineConfig, get_api_key

SUPPORTED_PROVIDERS = frozenset({"anthropic", "deepseek"})


class RunnerError(Exception):
    """Raised when an agent invocation fails after all retries."""


class UnsupportedProviderError(RunnerError):
    """Raised when the configured provider is not supported."""


@dataclass
class RunResult:
    """Result of a single agent invocation."""
    agent_id: str
    success: bool
    output: str
    tokens_used: int = 0
    error: str | None = None
    duration_ms: float = 0.0
    output_path: Path | None = None


def _build_deepseek_messages(system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    return messages


class AgentRunner:
    """Invokes a single agent via LLM API."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self._client: Any = None
        provider = config.model.provider
        if provider not in SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(
                f"Provider '{provider}' is not supported. "
                f"Supported: {', '.join(sorted(SUPPORTED_PROVIDERS))}. "
                f"To add a provider, implement its client in core/runner.py."
            )

    @property
    def client(self) -> Any:
        if self._client is None:
            provider = self.config.model.provider
            api_key = get_api_key(provider)
            if provider == "anthropic":
                import anthropic
                self._client = anthropic.Anthropic(api_key=api_key)
            elif provider == "deepseek":
                import openai
                self._client = openai.OpenAI(
                    api_key=api_key,
                    base_url="https://api.deepseek.com",
                )
        return self._client

    def run(self, agent_id: str, system_prompt: str, user_prompt: str) -> RunResult:
        """Invoke the LLM for a single agent. Returns structured result."""
        t0 = time.perf_counter()
        provider = self.config.model.provider

        last_error: str | None = None
        for attempt in range(self.config.retry + 1):
            try:
                if provider == "anthropic":
                    msg = self.client.messages.create(
                        model=self.config.model.model,
                        max_tokens=self.config.model.max_tokens,
                        temperature=self.config.model.temperature,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt}],
                    )
                    output = msg.content[0].text
                    tokens = msg.usage.output_tokens if msg.usage else 0
                elif provider == "deepseek":
                    resp = self.client.chat.completions.create(
                        model=self.config.model.model,
                        max_tokens=self.config.model.max_tokens,
                        temperature=self.config.model.temperature,
                        messages=_build_deepseek_messages(system_prompt, user_prompt),
                    )
                    output = resp.choices[0].message.content or ""
                    tokens = resp.usage.completion_tokens if resp.usage else 0

                elapsed = (time.perf_counter() - t0) * 1000
                return RunResult(
                    agent_id=agent_id,
                    success=True,
                    output=output,
                    tokens_used=tokens,
                    duration_ms=elapsed,
                )

            except Exception as e:
                last_error = str(e)
                if attempt < self.config.retry:
                    wait = 2 ** attempt
                    time.sleep(wait)
                continue

        elapsed = (time.perf_counter() - t0) * 1000
        return RunResult(
            agent_id=agent_id,
            success=False,
            output="",
            error=last_error,
            duration_ms=elapsed,
        )
