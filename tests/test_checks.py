"""Tests for core/checks.py"""
import shutil
import tempfile
from pathlib import Path

from core.checks import check_pipeline


def _write_agent(root: Path, agent_id: str, upstream: list[str], downstream: list[str]) -> None:
    agent_dir = root / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    agent_dir.joinpath("agent.md").write_text(
        "\n".join(
            [
                "---",
                f'id: "{agent_id}"',
                f'name: "{agent_id}"',
                f'title: "{agent_id}"',
                f'role: "{agent_id}"',
                f"upstream: {upstream}",
                f"downstream: {downstream}",
                "---",
                "# Role",
            ]
        ),
        encoding="utf-8",
    )
    agent_dir.joinpath("template.md").write_text("# Template\n", encoding="utf-8")
    agent_dir.joinpath("checklist.md").write_text("# Checklist\n", encoding="utf-8")


def test_check_pipeline_requires_reciprocal_links():
    """A downstream link must be mirrored by the child agent's upstream list."""
    tmp_root = Path(tempfile.mkdtemp())
    try:
        _write_agent(tmp_root, "01-pm", [], ["02-mechanical"])
        _write_agent(tmp_root, "02-mechanical", [], [])

        issues = check_pipeline(tmp_root)

        assert any("does not list '01-pm' as upstream" in issue for issue in issues)
        assert any("missing upstream agent" in issue for issue in issues)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
