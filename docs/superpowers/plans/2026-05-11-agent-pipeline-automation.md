# Agent Pipeline Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the document-template Agent pipeline into an LLM-driven automated workflow where each Agent invokes Claude API with its agent.md as system prompt, upstream documents as context, and produces structured output documents. Every Agent is fully independent — no shared in-memory state, communication only through filesystem documents.

**Architecture:** Four new core modules — `config.py` (model/provider config via YAML + env vars), `context.py` (prompt assembly from agent definition + upstream docs), `runner.py` (single-agent LLM invocation with retry), `engine.py` (orchestrator with `run_single` for isolated agent execution and `run_all` for full pipeline). CLI gains `pipeline run --agent <id>` (single agent), `pipeline run --from <id>` (resume), and `pipeline config` commands. Agents communicate only through filesystem documents — no shared memory, no IPC. Multiple terminal windows can run different agents concurrently for different projects.

**Tech Stack:** Python 3.12+, anthropic SDK, Pydantic v2, Click, PyYAML, Rich (progress display)

---

## File Map

| File | Responsibility | Action |
|------|---------------|--------|
| `core/config.py` | Model config, API keys, pipeline settings | Create |
| `core/context.py` | Assemble system prompt + user context for LLM call | Create |
| `core/runner.py` | Single-agent LLM invocation with retry + streaming | Create |
| `core/engine.py` | Sequential pipeline orchestrator, status tracking | Create |
| `core/schema.py` | Add `PipelineConfig` model | Modify |
| `cli/__init__.py` | Add `run` and `config` commands | Modify |
| `pyproject.toml` | Add anthropic, rich dependencies | Modify |
| `pipeline.yaml` | Default pipeline configuration file | Create |
| `.env.example` | Environment variable template | Create |

---

### Task 1: Pipeline Configuration (`core/config.py`)

**Files:**
- Create: `core/config.py`
- Modify: `core/schema.py` (add PipelineConfig model)
- Create: `pipeline.yaml`
- Create: `.env.example`

- [ ] **Step 1: Add PipelineConfig to schema.py**

Add to `core/schema.py` after the existing `PipelineStatus` class:

```python
class ModelConfig(BaseModel):
    """LLM model configuration."""
    model_config = ConfigDict(extra="forbid")

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 8192
    temperature: float = 0.3


class PipelineConfig(BaseModel):
    """Top-level pipeline configuration."""
    model_config = ConfigDict(extra="forbid")

    model: ModelConfig = Field(default_factory=ModelConfig)
    retry: int = Field(default=2, description="Max retries per agent on failure")
    output_dir: str = "examples"
    verbose: bool = False
```

- [ ] **Step 2: Write core/config.py**

```python
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
```

- [ ] **Step 3: Write pipeline.yaml (default config)**

```yaml
# Agent Pipeline configuration
# API keys come from environment variables — NEVER put them here.

model:
  provider: anthropic        # anthropic | openai | deepseek
  model: claude-sonnet-4-6   # or claude-opus-4-7, deepseek-v4-pro
  max_tokens: 8192
  temperature: 0.3

retry: 2                     # max retry attempts on LLM call failure
output_dir: examples         # where project output documents go
verbose: false               # extra logging
```

- [ ] **Step 4: Write .env.example**

```
# Copy this file to .env and fill in your API keys
ANTHROPIC_API_KEY=sk-ant-...
# DEEPSEEK_API_KEY=sk-...
# OPENAI_API_KEY=sk-...
```

- [ ] **Step 5: Verify config loads**

Run: `cd D:\work\agent-pipeline && uv run python -c "from core.config import load_config; from pathlib import Path; c = load_config(Path('.')); print(c.model.model)"`

Expected: `claude-sonnet-4-6`

- [ ] **Step 6: Commit**

```bash
git add core/config.py core/schema.py pipeline.yaml .env.example
git commit -m "feat: add pipeline configuration loader"
```

---

### Task 2: Prompt Context Builder (`core/context.py`)

**Files:**
- Create: `core/context.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_context.py`:

```python
"""Tests for core/context.py"""
from pathlib import Path
from core.context import build_agent_prompt, AgentContext


def test_build_agent_prompt_returns_correct_structure():
    agent_body = "# Role\nTest engineer.\n\n# Output\n## Section 1"
    template_body = "## Section 1\n<!-- comment -->"
    upstream_docs = {"01-pm": "Product spec content here."}

    ctx = AgentContext(
        agent_id="02-mechanical",
        agent_body=agent_body,
        template_body=template_body,
        upstream_docs=upstream_docs,
    )

    system, user = build_agent_prompt(ctx)

    assert "Test engineer" in system
    assert "Output" in system
    assert "Product spec content here" in user
    assert "## Section 1" in user
    assert "<!-- comment -->" not in user  # HTML comments stripped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\work\agent-pipeline && uv run pytest tests/test_context.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write core/context.py**

```python
"""
Assemble LLM prompt context from agent definition, template, and upstream documents.

System prompt = agent.md body (role, goals, constraints, principles)
User prompt   = upstream documents (if any) + template.md body (output guidance)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core.template import load_agent_doc, load_template

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass
class AgentContext:
    """All context needed to invoke a single agent."""
    agent_id: str
    agent_body: str
    template_body: str
    upstream_docs: dict[str, str] = field(default_factory=dict)


def _strip_html_comments(text: str) -> str:
    """Remove HTML comments from markdown template body."""
    return HTML_COMMENT_RE.sub("", text)


def _build_system_prompt(agent_body: str) -> str:
    """Build system prompt from agent.md body.

    The agent.md already contains: # 角色, # 行业背景, # 设计目标,
    # 输出, # 设计原则/约束. We use it verbatim as the system prompt.
    """
    return agent_body.strip()


def _build_user_prompt(ctx: AgentContext) -> str:
    """Build user prompt from upstream documents + output template."""
    parts: list[str] = []

    if ctx.upstream_docs:
        parts.append("# 上游输入文档\n")
        for agent_id, content in ctx.upstream_docs.items():
            parts.append(f"## 来自 {agent_id}\n\n{content}\n")

    # Template as output guidance
    clean_template = _strip_html_comments(ctx.template_body)
    parts.append(f"# 输出模板（请按此结构填充）\n\n{clean_template}")

    parts.append(
        "\n# 指令\n"
        "请按照上述输出模板的结构，基于上游输入文档，产出完整的方案文档。\n"
        "- 用专业工程语言填充每个章节，不要保留注释占位符\n"
        "- 所有量化参数需基于上游输入中的约束进行计算或合理取值\n"
        "- 如果某章节因上游信息不足无法填写，请标注「待上游确认：需要 XXX 数据」\n"
        "- 输出纯 Markdown，不要输出前言/后记/解释说明"
    )

    return "\n\n".join(parts)


def build_agent_prompt(ctx: AgentContext) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for an agent LLM call."""
    system = _build_system_prompt(ctx.agent_body)
    user = _build_user_prompt(ctx)
    return system, user


def load_agent_context(root: Path, agent_id: str, project_dir: Path) -> AgentContext:
    """Load all context needed to invoke an agent from disk.

    Args:
        root: Agent-pipeline project root (contains agents/).
        agent_id: e.g. '02-mechanical'.
        project_dir: Project output directory (e.g. examples/pic/).
    """
    agent_dir = root / "agents" / agent_id
    fm, agent_body = load_agent_doc(agent_dir)
    _, template_body = load_template(agent_dir)

    # Collect upstream documents
    upstream_ids: list[str] = fm.get("upstream", [])
    upstream_docs: dict[str, str] = {}
    for uid in upstream_ids:
        doc_path = project_dir / f"{uid}-方案.md"
        if doc_path.exists():
            upstream_docs[uid] = doc_path.read_text(encoding="utf-8")

    return AgentContext(
        agent_id=agent_id,
        agent_body=agent_body,
        template_body=template_body,
        upstream_docs=upstream_docs,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:\work\agent-pipeline && uv run pytest tests/test_context.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/context.py tests/test_context.py
git commit -m "feat: add prompt context builder for agent LLM calls"
```

---

### Task 3: Single Agent Runner (`core/runner.py`)

**Files:**
- Create: `core/runner.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_runner.py`:

```python
"""Tests for core/runner.py"""
from pathlib import Path
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\work\agent-pipeline && uv run pytest tests/test_runner.py -v`
Expected: FAIL

- [ ] **Step 3: Write core/runner.py**

```python
"""
Single-agent LLM runner.

Invokes Claude API (via anthropic SDK) with assembled prompt context.
Handles retries, streaming display, and structured result capture.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from anthropic.types import Message

from core.config import PipelineConfig, get_api_key


class RunnerError(Exception):
    """Raised when an agent invocation fails after all retries."""


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
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            api_key = get_api_key(self.config.model.provider)
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def run(self, agent_id: str, system_prompt: str, user_prompt: str) -> RunResult:
        """Invoke the LLM for a single agent. Returns structured result."""
        t0 = time.perf_counter()

        last_error: str | None = None
        for attempt in range(self.config.retry + 1):
            try:
                msg: Message = self.client.messages.create(
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
                    wait = 2 ** attempt  # 1s, 2s, 4s backoff
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:\work\agent-pipeline && uv run pytest tests/test_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/runner.py tests/test_runner.py
git commit -m "feat: add single-agent LLM runner with retry"
```

---

### Task 4: Pipeline Engine (`core/engine.py`)

**Files:**
- Create: `core/engine.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_engine.py`:

```python
"""Tests for core/engine.py"""
from pathlib import Path
from core.engine import PipelineEngine, EngineResult
from core.schema import PipelineStage


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\work\agent-pipeline && uv run pytest tests/test_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Write core/engine.py**

```python
"""
Pipeline execution engine.

Orchestrates sequential agent execution: for each agent in pipeline order,
load upstream documents, build prompt, invoke runner, write output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.config import PipelineConfig, load_config
from core.context import AgentContext, build_agent_prompt, load_agent_context
from core.runner import AgentRunner, RunResult
from core.template import all_agents, load_agent_doc


@dataclass
class EngineResult:
    """Result of a full pipeline run."""
    project: str
    completed_agents: list[str] = field(default_factory=list)
    failed_agents: list[str] = field(default_factory=list)
    total_tokens: int = 0
    total_duration_ms: float = 0.0

    @property
    def all_success(self) -> bool:
        return len(self.failed_agents) == 0

    @property
    def summary(self) -> str:
        lines = [
            f"Project: {self.project}",
            f"Completed: {len(self.completed_agents)}/{len(self.completed_agents) + len(self.failed_agents)}",
            f"Tokens: {self.total_tokens:,}",
            f"Duration: {self.total_duration_ms/1000:.1f}s",
        ]
        if self.failed_agents:
            lines.append(f"Failed: {', '.join(self.failed_agents)}")
        return "\n".join(lines)


class PipelineEngine:
    """Runs the agent pipeline for a project.

    Each agent is fully independent:
    - Reads upstream documents from filesystem (not shared memory)
    - Writes its output to its own document file
    - Failure of one agent does not corrupt another agent's output
    - Any agent can be run standalone without running the full pipeline
    """

    def __init__(self, root: Path, config: PipelineConfig | None = None) -> None:
        self.root = root
        self.config = config or load_config(root)
        self.runner = AgentRunner(self.config)

    def run_single(self, project_name: str, agent_id: str) -> RunResult:
        """Run a single agent independently. Reads upstream docs, writes output."""
        project_dir = self.root / self.config.output_dir / project_name
        if not project_dir.exists():
            project_dir.mkdir(parents=True)

        output_path = project_dir / f"{agent_id}-方案.md"

        ctx = load_agent_context(self.root, agent_id, project_dir)
        system, user = build_agent_prompt(ctx)

        if self.config.verbose:
            upstream_list = list(ctx.upstream_docs.keys())
            print(f"  [{agent_id}] upstream: {upstream_list or '(none — first agent)'}")
            print(f"  [{agent_id}] invoking ({len(system)} sys + {len(user)} user chars)...")

        result = self.runner.run(agent_id, system, user)

        if result.success:
            output_path.write_text(result.output, encoding="utf-8")
            print(f"  [{agent_id}] done — {result.tokens_used} tokens, {result.duration_ms/1000:.1f}s")
        else:
            print(f"  [{agent_id}] FAILED — {result.error}")

        return result

    def run_all(self, project_name: str, from_agent: str | None = None) -> EngineResult:
        """Execute all agents sequentially. Each agent runs independently.

        Args:
            project_name: Project directory name under output_dir.
            from_agent: If set, skip agents before this one (their outputs must exist).
        """
        agent_dirs = all_agents(self.root)
        result = EngineResult(project=project_name)

        skip = from_agent is not None
        for agent_dir in agent_dirs:
            fm, _ = load_agent_doc(agent_dir)
            agent_id = str(fm.get("id", agent_dir.name))

            if skip and agent_id != from_agent:
                continue
            skip = False

            run_result = self.run_single(project_name, agent_id)
            result.total_tokens += run_result.tokens_used
            result.total_duration_ms += run_result.duration_ms

            if run_result.success:
                result.completed_agents.append(agent_id)
            else:
                result.failed_agents.append(agent_id)
                break  # Stop pipeline on first failure

        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:\work\agent-pipeline && uv run pytest tests/test_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/engine.py tests/test_engine.py
git commit -m "feat: add pipeline execution engine"
```

---

### Task 5: CLI Integration (`cli/__init__.py`)

**Files:**
- Modify: `cli/__init__.py`

- [ ] **Step 1: Update CLI with run and config commands**

Replace `cli/__init__.py` with the complete updated version:

```python
"""
pipeline CLI — agent-pipeline project management and execution tool.
"""
from __future__ import annotations

from pathlib import Path

import click

from core.checks import check_pipeline
from core.config import load_config
from core.engine import PipelineEngine
from core.template import (
    all_agents,
    list_agents,
    load_agent_doc,
    load_template,
)


@click.group()
def cli() -> None:
    """Agent pipeline — 硬件产品开发多 Agent 协作框架."""


@cli.command()
@click.argument("project_name")
def new(project_name: str) -> None:
    """Create a new project from agent templates."""
    root = Path.cwd()
    project_dir = root / "examples" / project_name
    if project_dir.exists():
        click.secho(f"Project '{project_name}' already exists.", fg="red")
        return

    project_dir.mkdir(parents=True)
    for agent_dir in all_agents(root):
        tmpl_path = agent_dir / "template.md"
        if tmpl_path.exists():
            _, body = load_template(agent_dir)
            out = project_dir / f"{agent_dir.name}-方案.md"
            out.write_text(body, encoding="utf-8")
            click.echo(f"  created {out.relative_to(root)}")

    click.secho(f"\nProject '{project_name}' created at {project_dir}", fg="green")


@cli.command()
def list() -> None:
    """List all defined agents and their status."""
    root = Path.cwd()
    agents = list_agents(root)
    if not agents:
        click.secho("No agents found.", fg="yellow")
        return

    click.echo(f"{'ID':<16} {'Title':<24} {'Upstream':<20} {'Downstream':<20}")
    click.echo("-" * 80)
    for a in agents:
        up = ", ".join(a.get("upstream", []))
        dw = ", ".join(a.get("downstream", []))
        click.echo(f"{a['id']:<16} {a['title']:<24} {up:<20} {dw:<20}")


@cli.command()
def check() -> None:
    """Validate pipeline integrity (interface consistency, missing files)."""
    root = Path.cwd()
    issues = check_pipeline(root)
    if not issues:
        click.secho("Pipeline OK — all agents connected, all files present.", fg="green")
    else:
        click.secho(f"Found {len(issues)} issue(s):", fg="red")
        for i in issues:
            click.echo(f"  - {i}")


@cli.command()
@click.argument("agent_id")
def show(agent_id: str) -> None:
    """Show agent definition."""
    root = Path.cwd()
    agent_dir = root / "agents" / agent_id
    if not agent_dir.exists():
        click.secho(f"Agent '{agent_id}' not found.", fg="red")
        return

    fm, body = load_agent_doc(agent_dir)
    click.secho(f"{fm['title']} ({fm['id']})", fg="cyan", bold=True)
    click.echo()
    click.echo(body)


@cli.command()
def status() -> None:
    """Show pipeline project status."""
    root = Path.cwd()
    status_path = root / "STATUS.md"
    if not status_path.exists():
        click.secho("No STATUS.md found in current directory.", fg="yellow")
        return

    content = status_path.read_text(encoding="utf-8")
    click.echo(content)


@cli.command()
@click.argument("project_name")
@click.option("--agent", "agent_id", default=None, help="Run a single agent independently (e.g. 03-optics)")
@click.option("--from", "from_agent", default=None, help="Resume pipeline from a specific agent")
def run(project_name: str, agent_id: str | None, from_agent: str | None) -> None:
    """Execute agents for a project.

    Each agent is fully independent — reads upstream docs from disk,
    writes its own output. Multiple terminal windows can run different
    agents simultaneously for different projects.

    Examples:
      pipeline run pic                    # full pipeline
      pipeline run pic --agent 03-optics  # single agent, isolated
      pipeline run pic --from 04-motion   # resume from mid-pipeline
    """
    root = Path.cwd()
    config = load_config(root)
    engine = PipelineEngine(root, config)

    if agent_id:
        click.secho(f"Running single agent '{agent_id}' for '{project_name}'...", fg="cyan", bold=True)
        result = engine.run_single(project_name, agent_id)
        click.echo()
        if result.success:
            click.secho(f"Agent {agent_id} complete — {result.tokens_used} tokens, {result.duration_ms/1000:.1f}s", fg="green")
        else:
            click.secho(f"Agent {agent_id} FAILED — {result.error}", fg="red")
    else:
        if from_agent:
            click.secho(f"Running pipeline for '{project_name}' from {from_agent}...", fg="cyan", bold=True)
        else:
            click.secho(f"Running pipeline for '{project_name}'...", fg="cyan", bold=True)

        result = engine.run_all(project_name, from_agent=from_agent)

        click.echo()
        if result.all_success:
            click.secho(f"Pipeline complete: {result.summary}", fg="green")
        else:
            click.secho(f"Pipeline incomplete: {result.summary}", fg="yellow")


@cli.command()
def config_show() -> None:
    """Show current pipeline configuration."""
    root = Path.cwd()
    config = load_config(root)

    click.echo(f"Provider:   {config.model.provider}")
    click.echo(f"Model:      {config.model.model}")
    click.echo(f"Max tokens: {config.model.max_tokens}")
    click.echo(f"Temperature:{config.model.temperature}")
    click.echo(f"Retry:      {config.retry}")
    click.echo(f"Output dir: {config.output_dir}")
    click.echo(f"Verbose:    {config.verbose}")


if __name__ == "__main__":
    cli()
```

- [ ] **Step 2: Verify CLI commands are registered**

Run: `cd D:\work\agent-pipeline && uv run python -c "from cli import cli; print([cmd for cmd in cli.commands])"`
Expected: `['new', 'list', 'check', 'show', 'status', 'run', 'config_show']` — `run` accepts `--agent` (single) and `--from` (resume)

- [ ] **Step 3: Commit**

```bash
git add cli/__init__.py
git commit -m "feat: add pipeline run and config CLI commands"
```

---

### Task 6: Dependencies and Final Integration

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update pyproject.toml with new dependencies**

Edit `pyproject.toml` — change dependencies to:

```toml
dependencies = [
    "click>=8.1",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "anthropic>=0.40.0",
    "rich>=13.0",
]
```

- [ ] **Step 2: Install and verify**

Run:
```bash
cd D:\work\agent-pipeline
uv sync
uv run pipeline check
```

Expected: `Pipeline OK — all agents connected, all files present.`

- [ ] **Step 3: Full integration smoke test**

Run:
```bash
cd D:\work\agent-pipeline
uv run pipeline config_show
uv run pipeline list
```

Expected: config and agent list displayed correctly.

- [ ] **Step 4: Create tests directory __init__**

```bash
mkdir D:\work\agent-pipeline\tests
```

Create `tests/__init__.py` (empty).

- [ ] **Step 5: Run all tests**

```bash
cd D:\work\agent-pipeline && uv run pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 6: Final commit**

```bash
git add pyproject.toml tests/ uv.lock
git commit -m "chore: add anthropic SDK and test infrastructure"
```

---

### Task 7: End-to-End Manual Verification

- [ ] **Step 1: Create a test project**

```bash
cd D:\work\agent-pipeline
uv run pipeline new demo
```

Expected: 6 template files created under `examples/demo/`.

- [ ] **Step 2: Manually fill in 01-pm upstream doc**

Since 01-pm has no upstream, write a brief product spec into `examples/demo/01-pm-方案.md`:

```
# 产品规格书

## 检测对象
- 材质：碳钢棒材
- 直径范围：φ10-50mm
- 表面状态：磨削后

## 缺陷分类
| 类型 | 最小尺寸 | 检出率 |
|------|---------|--------|
| 划痕 | 0.1mm宽×5mm长 | ≥98% |
| 凹坑 | φ0.3mm | ≥95% |

## 生产节拍
- 最大线速度：2 m/s
```

- [ ] **Step 3: Test single-agent execution**

```bash
cd D:\work\agent-pipeline
uv run pipeline run demo --agent 02-mechanical
```

Expected: Only 02-mechanical runs, reads 01-pm doc, writes 02-mechanical-方案.md independently.

- [ ] **Step 4: Verify agent isolation**

Open two terminal windows:
- Window 1: `uv run pipeline run demo --agent 03-optics`
- Window 2: check `examples/demo/` — only 03-optics output is touched

No shared state, no cross-contamination.

- [ ] **Step 5: Run full pipeline (requires ANTHROPIC_API_KEY)**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
cd D:\work\agent-pipeline
uv run pipeline run demo
```

Expected: Pipeline executes 01-06 sequentially, each producing output docs independently.

- [ ] **Step 6: Verify output**

```bash
ls examples/demo/
```

Expected: `01-pm-方案.md` through `06-review-方案.md` all present with non-empty content.

---

## Self-Review

### 1. Spec coverage
- Pipeline config with env vars: Task 1
- Prompt assembly from agent.md + upstream: Task 2
- LLM invocation with retry: Task 3
- Sequential pipeline orchestration: Task 4
- CLI `run` command: Task 5
- Dependencies: Task 6
- E2E verification: Task 7

### 2. Placeholder scan
No TBD/TODO found. All code steps have complete implementations.

### 3. Type consistency
- `AgentContext` defined in Task 2, used by `build_agent_prompt()` in Task 2 and `load_agent_context()` in Task 2
- `RunResult` defined in Task 3, used by `AgentRunner.run()` in Task 3 and `PipelineEngine.run()` in Task 4
- `EngineResult` defined in Task 4, used by CLI `run` command in Task 5
- All cross-module references match across tasks.
