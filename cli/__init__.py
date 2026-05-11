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
