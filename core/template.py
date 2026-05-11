"""
Template loading and Markdown+YAML frontmatter parsing.

Agent definition files (agent.md, template.md, checklist.md) use YAML frontmatter
followed by Markdown body. This module handles parsing and structured access.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split frontmatter dict and markdown body from raw text."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm = yaml.safe_load(m.group(1)) or {}
    body = text[m.end():]
    return fm, body


def load_agent_doc(agent_dir: Path) -> tuple[dict[str, object], str]:
    """Load and parse an agent.md file."""
    path = agent_dir / "agent.md"
    if not path.exists():
        raise FileNotFoundError(f"Agent definition not found: {path}")
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def load_template(agent_dir: Path) -> tuple[dict[str, object], str]:
    """Load and parse a template.md file."""
    path = agent_dir / "template.md"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def load_checklist(agent_dir: Path) -> tuple[dict[str, object], str]:
    """Load and parse a checklist.md file."""
    path = agent_dir / "checklist.md"
    if not path.exists():
        raise FileNotFoundError(f"Checklist not found: {path}")
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def all_agents(root: Path) -> list[Path]:
    """Return sorted list of agent directories under root/agents/."""
    agents_dir = root / "agents"
    if not agents_dir.exists():
        return []
    dirs = sorted(
        d for d in agents_dir.iterdir()
        if d.is_dir() and d.name[0].isdigit()
    )
    return dirs


def list_agents(root: Path) -> list[dict[str, object]]:
    """Get metadata for all agents."""
    result: list[dict[str, object]] = []
    for d in all_agents(root):
        try:
            fm, _ = load_agent_doc(d)
            result.append(fm)
        except FileNotFoundError:
            continue
    return result
