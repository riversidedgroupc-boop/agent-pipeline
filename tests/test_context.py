"""Tests for core/context.py"""
from pathlib import Path
from core.context import (
    AgentContext,
    _strip_html_comments,
    build_agent_prompt,
    load_agent_context,
)


def test_strip_html_comments():
    result = _strip_html_comments("## Section\n<!-- comment -->\ncontent")
    assert "<!-- comment -->" not in result
    assert "## Section" in result
    assert "content" in result


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
    assert "<!-- comment -->" not in user
    assert "来自 01-pm" in user
    assert "输出模板" in user
    assert "指令" in user


def test_build_agent_prompt_no_upstream():
    ctx = AgentContext(
        agent_id="01-pm",
        agent_body="# Role\nPM",
        template_body="## Section",
        upstream_docs={},
    )

    system, user = build_agent_prompt(ctx)

    assert system == "# Role\nPM"
    assert "# 上游输入文档" not in user
    assert "## Section" in user


def test_load_agent_context_reads_latest_upstream_version(tmp_path: Path):
    root = tmp_path
    agent_dir = root / "agents" / "02-mechanical"
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.md").write_text(
        "---\n"
        "id: 02-mechanical\n"
        "name: mechanical\n"
        "title: Mechanical\n"
        "role: Engineer\n"
        "upstream:\n"
        "  - 01-pm\n"
        "---\n"
        "# Role\nEngineer\n",
        encoding="utf-8",
    )
    (agent_dir / "template.md").write_text("## Output\n", encoding="utf-8")
    project_dir = root / "examples" / "demo"
    project_dir.mkdir(parents=True)
    (project_dir / "01-pm-方案.md").write_text("old PM output", encoding="utf-8")
    (project_dir / "01-pm-方案-v2.md").write_text("new PM output", encoding="utf-8")

    ctx = load_agent_context(root, "02-mechanical", project_dir)

    assert ctx.upstream_docs["01-pm"] == "new PM output"
