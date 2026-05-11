"""
Single-agent LLM runner.

Invokes LLM API with assembled prompt context.
Currently supports Anthropic provider. Openai/Deepseek stubs raise clear errors.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from core.config import PipelineConfig, get_api_key

SUPPORTED_PROVIDERS = frozenset({"anthropic"})


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
            import anthropic
            api_key = get_api_key(self.config.model.provider)
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def run(self, agent_id: str, system_prompt: str, user_prompt: str) -> RunResult:
        """Invoke the LLM for a single agent. Returns structured result."""
        t0 = time.perf_counter()

        last_error: str | None = None
        for attempt in range(self.config.retry + 1):
            try:
                msg = self.client.messages.create(
                    model=self.config.model.model,
                    max_tokens=self.config.model.max_tokens,
                    temperature=self.config.model.temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )

                output = msg.content[0].text
                tokens = msg.usage.output_tokens if msg.usage else 0
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
