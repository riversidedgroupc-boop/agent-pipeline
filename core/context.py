"""
Assemble LLM prompt context from agent definition, template, and upstream documents.

System prompt = agent.md body (role, goals, constraints, principles)
User prompt   = upstream documents (if any) + template.md body (output guidance)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core.outputs import latest_agent_output_path
from core.template import load_agent_doc, load_template

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass
class AgentContext:
    """All context needed to invoke a single agent."""
    agent_id: str
    agent_body: str
    template_body: str
    upstream_docs: dict[str, str] = field(default_factory=dict)
    requirements: str = ""


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

    # Customer requirements always come first
    if ctx.requirements:
        parts.append("# 客户需求\n")
        parts.append(ctx.requirements + "\n")

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
        doc_path = latest_agent_output_path(project_dir, uid)
        if doc_path.exists():
            upstream_docs[uid] = doc_path.read_text(encoding="utf-8")

    # Read customer requirements (shared input for all agents)
    requirements = ""
    req_path = project_dir / "requirements.md"
    if req_path.exists():
        requirements = req_path.read_text(encoding="utf-8").strip()

    return AgentContext(
        agent_id=agent_id,
        agent_body=agent_body,
        template_body=template_body,
        upstream_docs=upstream_docs,
        requirements=requirements,
    )
