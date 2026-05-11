"""Tests for core/context.py"""
from pathlib import Path
from core.context import build_agent_prompt, AgentContext, _strip_html_comments


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
