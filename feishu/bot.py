"""
Feishu bot — format agent outputs, push to groups, collect feedback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.template import load_agent_doc, load_template, all_agents
from feishu.client import FeishuClient, FeishuError
from feishu.monitor import get_pipeline_status, get_model_config, get_project_dir


@dataclass
class Feedback:
    """Feedback collected from a Feishu reply."""
    agent_id: str
    reviewer: str
    content: str
    timestamp: str = ""


def format_agent_for_post(agent_id: str, agent_title: str, output: str) -> tuple[str, list[list[dict[str, Any]]]]:
    """Format an agent's output as a Feishu post message.

    Returns (title, paragraphs) for send_post().
    """
    title = f"[{agent_title}方案 · 请审阅]"

    # Truncate output to fit Feishu post limits (roughly 30KB)
    body = output
    if len(body) > 25000:
        body = body[:25000] + "\n\n...(内容过长，完整方案请查看 GeniusForge)"

    paragraphs: list[list[dict[str, Any]]] = []

    # First paragraph: header info
    paragraphs.append([
        {"tag": "text", "text": f"Agent: {agent_id} ({agent_title})\n请审阅以下方案，回复修改意见或发送 ✅ 确认通过。"}
    ])

    # Split body into sections by ## headings
    sections = re.split(r"\n(?=## )", body)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        # Each section as a text paragraph
        # Truncate very long sections
        if len(section) > 3000:
            section = section[:3000] + "\n...(截断)"
        paragraphs.append([{"tag": "text", "text": section}])

    return title, paragraphs


def parse_feedback_from_message(text: str) -> str:
    """Clean up a message to extract feedback content.

    Removes @mentions of the bot and strips whitespace.
    """
    # Remove @bot mentions
    cleaned = re.sub(r"@\S*机器人\S*", "", text)
    cleaned = re.sub(r"@\S*bot\S*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    return cleaned


def parse_bot_command(text: str) -> tuple[str, str]:
    """Parse a bot command from message text.

    Returns (command, args) where command is one of:
    'new_project', 'status', 'view', 'rerun', 'help', 'approve', 'feedback', 'unknown'
    """
    text = text.strip()
    # New project
    if re.search(r"(新建项目|创建项目|新项目|new project)", text):
        return ("new_project", "")
    if re.search(r"(状态|进度|status)", text):
        return ("status", "")
    m = re.search(r"(?:查看|view)\s*(\S+)", text)
    if m:
        return ("view", m.group(1))
    m = re.search(r"(?:重跑|rerun|重新生成)\s*(\S+)", text)
    if m:
        return ("rerun", m.group(1))
    if re.search(r"(帮助|help|命令)", text):
        return ("help", "")
    if re.search(r"✅|确认|通过|OK|ok|没问题", text):
        return ("approve", "")
    return ("feedback", text)


# Agent role mapping for @mentions
AGENT_ROLES: dict[str, str] = {
    "01-pm": "产品经理",
    "02-mechanical": "机械结构工程师",
    "03-optics": "光学工程师",
    "04-motion": "运动控制工程师",
    "05-algorithm": "算法工程师",
    "06-review": "整机评审工程师",
}


def get_agent_role(agent_id: str) -> str:
    return AGENT_ROLES.get(agent_id, agent_id)


def _find_blocking(root: Path, project_name: str, agent_id: str) -> list[str]:
    """Find which upstream agents are blocking this agent."""
    AGENT_ORDER = ["01-pm", "02-mechanical", "03-optics", "04-motion", "05-algorithm", "06-review"]
    idx = AGENT_ORDER.index(agent_id)
    upstream = AGENT_ORDER[:idx]
    if not upstream:
        return []
    project_dir = get_project_dir(root, project_name)
    return [u for u in upstream if not (project_dir / f"{u}-方案.docx").exists()]


def build_status_post(root: Path, project_name: str) -> tuple[str, list[list[dict[str, Any]]]]:
    """Build an enhanced status post with per-agent token, cost, and status info."""
    states = get_pipeline_status(root, project_name)

    title = f"📊 项目 {project_name} 流水线状态"

    paragraphs: list[list[dict[str, Any]]] = []
    paragraphs.append([{"tag": "text", "text": "━━━━━━━━━━━━━━━━━━━━"}])

    total_tokens = 0
    total_cost = 0.0
    done_count = 0

    for s in states:
        icon = s.icon
        tokens_str = f"{s.tokens_used / 1000:.1f}k" if s.tokens_used else "—"
        cost_str = f"¥{s.cost_cny:.2f}" if s.cost_cny else "—"
        size_str = f"{s.output_size_kb:.1f}KB" if s.output_size_kb > 0 else "—"

        line_parts = [
            f"{icon} {s.agent_id} {s.label}",
            f"   状态：{s.status_text} | Token：{tokens_str} | 成本：{cost_str} | 方案：{size_str}",
        ]

        if s.status == "blocked":
            blocking = _find_blocking(root, project_name, s.agent_id)
            if blocking:
                line_parts.append(f"   阻塞原因：等待 {'、'.join(blocking)} 输出")

        if s.status == "failed" and s.error:
            line_parts.append(f"   错误：{s.error}" if len(s.error) <= 100 else f"   错误：{s.error[:100]}...")

        paragraphs.append([{"tag": "text", "text": "\n".join(line_parts)}])

        total_tokens += s.tokens_used
        total_cost += s.cost_cny
        if s.status == "done":
            done_count += 1

    # Summary line
    total = len(states)
    paragraphs.append([{"tag": "text", "text": "━━━━━━━━━━━━━━━━━━━━"}])
    summary = f"📈 汇总：已完成 {done_count}/{total} | 总 Token：{total_tokens / 1000:.1f}k | 预估成本：¥{total_cost:.2f}"
    paragraphs.append([{"tag": "text", "text": summary}])

    return title, paragraphs


def build_help_post() -> tuple[str, list[list[dict[str, Any]]]]:
    """Build help message for bot commands."""
    title = "[帮助] GeniusForge 机器人命令"

    paragraphs: list[list[dict[str, Any]]] = [
        [{"tag": "text", "text": "@GeniusForge 支持以下命令："}],
        [{"tag": "text", "text": "新建项目 — 启动新项目：收集需求 → PM 方案 → 审批 → 全部 Agent 设计"}],
        [{"tag": "text", "text": "状态 — 查看流水线状态，含 Token 消耗与成本估算"}],
        [{"tag": "text", "text": "查看 <Agent> — 重新发送某个 Agent 的方案（如：查看 光学）"}],
        [{"tag": "text", "text": "重跑 <Agent> — 触发重新生成某个 Agent 方案（如：重跑 03-optics）"}],
        [{"tag": "text", "text": "帮助 — 显示此帮助信息"}],
        [{"tag": "text", "text": "\n反馈方式：直接回复机器人消息，输入修改建议即可。"}],
        [{"tag": "text", "text": "确认通过：回复 ✅ 或 确认。PM 方案通过后自动触发全部下游 Agent。"}],
    ]

    return title, paragraphs
