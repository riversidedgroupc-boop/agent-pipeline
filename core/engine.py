"""
Pipeline execution engine.

Orchestrates sequential agent execution: for each agent in pipeline order,
load upstream documents, build prompt, invoke runner, write output.

Every agent is independent -- reads from filesystem, writes to its own file.
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
            print(f"  [{agent_id}] upstream: {upstream_list or '(none -- first agent)'}")
            print(f"  [{agent_id}] invoking ({len(system)} sys + {len(user)} user chars)...")

        result = self.runner.run(agent_id, system, user)

        if result.success:
            output_path.write_text(result.output, encoding="utf-8")
            print(f"  [{agent_id}] done -- {result.tokens_used} tokens, {result.duration_ms/1000:.1f}s")
        else:
            print(f"  [{agent_id}] FAILED -- {result.error}")

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
