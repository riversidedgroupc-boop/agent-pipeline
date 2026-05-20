"""Helpers for locating agent output documents."""
from __future__ import annotations

import re
from pathlib import Path

_OUTPUT_RE = re.compile(r"^(?P<agent_id>.+)-方案-v(?P<version>\d+)\.md$")


def agent_output_path(project_dir: Path, agent_id: str) -> Path:
    """Return the canonical output path for an agent."""
    return project_dir / f"{agent_id}-方案.md"


def next_versioned_agent_output_path(project_dir: Path, agent_id: str) -> Path:
    """Return the next available versioned output path for an agent."""
    version = 2
    while (project_dir / f"{agent_id}-方案-v{version}.md").exists():
        version += 1
    return project_dir / f"{agent_id}-方案-v{version}.md"


def latest_agent_output_path(project_dir: Path, agent_id: str) -> Path:
    """Return the latest existing versioned output path, or the canonical path."""
    latest_version = 0
    latest_path = agent_output_path(project_dir, agent_id)

    for path in project_dir.glob(f"{agent_id}-方案-v*.md"):
        match = _OUTPUT_RE.match(path.name)
        if not match or match.group("agent_id") != agent_id:
            continue
        version = int(match.group("version"))
        if version > latest_version:
            latest_version = version
            latest_path = path

    return latest_path


# ── docx output paths ─────────────────────────────────────────────

_DOCX_OUTPUT_RE = re.compile(r"^(?P<agent_id>.+)-方案-v(?P<version>\d+)\.docx$")


def docx_output_path(project_dir: Path, agent_id: str) -> Path:
    """Return the canonical .docx output path for an agent."""
    return project_dir / f"{agent_id}-方案.docx"


def next_versioned_docx_output_path(project_dir: Path, agent_id: str) -> Path:
    """Return the next available versioned .docx output path for an agent."""
    version = 2
    while (project_dir / f"{agent_id}-方案-v{version}.docx").exists():
        version += 1
    return project_dir / f"{agent_id}-方案-v{version}.docx"


def latest_docx_output_path(project_dir: Path, agent_id: str) -> Path:
    """Return the latest existing versioned .docx path, or the canonical path."""
    latest_version = 0
    latest_path = docx_output_path(project_dir, agent_id)

    for docx_path in project_dir.glob(f"{agent_id}-方案-v*.docx"):
        match = _DOCX_OUTPUT_RE.match(docx_path.name)
        if not match or match.group("agent_id") != agent_id:
            continue
        version = int(match.group("version"))
        if version > latest_version:
            latest_version = version
            latest_path = docx_path

    return latest_path
