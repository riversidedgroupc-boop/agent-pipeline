"""
Feishu CLI commands — push agent outputs, collect feedback, interactive workflow.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import click

from core.config import load_config
from core.outputs import latest_agent_output_path, latest_docx_output_path
from core.template import all_agents, load_agent_doc
from feishu.client import FeishuClient, FeishuError, ChatMessage
from feishu.bot import (
    format_agent_for_post,
    parse_feedback_from_message,
    parse_bot_command,
    build_status_post,
    build_help_post,
    get_agent_role,
    Feedback,
)

# ── Project creation state machine ──────────────────────────────────────────

@dataclass
class ProjectState:
    """Tracks the multi-step project creation flow in a chat."""
    phase: str = "idle"  # idle | collecting_name | collecting_reqs | pm_approved | done
    project_name: str = ""
    requirements: str = ""
    pm_message_id: str = ""  # the Feishu message containing PM output (for approval lookup)


def _state_path(root: Path) -> Path:
    return root / ".geniusforge" / "project-states.json"


def _load_project_states(root: Path) -> dict[str, ProjectState]:
    path = _state_path(root)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: ProjectState(**v) for k, v in raw.items()}


def _save_project_states(root: Path, states: dict[str, ProjectState]) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = {k: {"phase": s.phase, "project_name": s.project_name,
               "requirements": s.requirements, "pm_message_id": s.pm_message_id}
           for k, s in states.items()}
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_next_project_name(root: Path, config) -> str:
    """Auto-increment project name: proj-001, proj-002, ..."""
    output_dir = root / config.output_dir
    existing = [d.name for d in output_dir.iterdir() if d.is_dir()] if output_dir.exists() else []
    n = 1
    while f"proj-{n:03d}" in existing:
        n += 1
    return f"proj-{n:03d}"


@click.group()
@click.option("--project", "-p", "project_name", default="pic", show_default=True,
              help="Project name under output_dir")
@click.pass_context
def feishu(ctx: click.Context, project_name: str) -> None:
    """Feishu bot — push scheme outputs, collect feedback."""
    ctx.ensure_object(dict)
    ctx.obj["project_name"] = project_name


@feishu.command()
def chats() -> None:
    """List Feishu chats the bot has joined."""
    client = FeishuClient()
    try:
        chat_list = client.list_chats()
    except FeishuError as e:
        click.secho(str(e), fg="red")
        return

    if not chat_list:
        click.secho("No chats found. Add the bot to a Feishu group first.", fg="yellow")
        return

    click.echo(f"{'Chat ID':<22} {'Name':<20} {'Description'}")
    click.echo("-" * 70)
    for c in chat_list:
        click.echo(f"{c['chat_id']:<22} {c['name']:<20} {c['description']}")


@feishu.command()
@click.option("--chat-id", required=True, help="Feishu group chat_id")
@click.argument("agent_id")
@click.pass_context
def push(ctx: click.Context, chat_id: str, agent_id: str) -> None:
    """Push an agent's output to a Feishu group."""
    root = Path.cwd()
    config = load_config(root)
    project_name: str = ctx.obj["project_name"]
    project_dir = root / config.output_dir / project_name

    output_path = latest_agent_output_path(project_dir, agent_id)
    if not output_path.exists():
        click.secho(f"File not found: {output_path}", fg="red")
        click.echo(f"Run 'pipeline run {project_name}' first to generate outputs.")
        return

    agent_dir = root / "agents" / agent_id
    fm, _ = load_agent_doc(agent_dir)
    title = str(fm.get("title", agent_id))
    output = output_path.read_text(encoding="utf-8")

    client = FeishuClient()
    try:
        post_title, paragraphs = format_agent_for_post(agent_id, title, output)
        msg_id = client.send_post(chat_id, post_title, paragraphs)
        _store_message_link(root, msg_id, agent_id)
        click.secho(f"Pushed {agent_id} to chat {chat_id}", fg="green")
        click.echo(f"  message_id: {msg_id}")
    except FeishuError as e:
        click.secho(str(e), fg="red")


@feishu.command()
@click.option("--chat-id", required=True, help="Feishu group chat_id")
@click.pass_context
def push_all(ctx: click.Context, chat_id: str) -> None:
    """Push ALL agent outputs to a Feishu group in sequence."""
    root = Path.cwd()
    config = load_config(root)
    project_name: str = ctx.obj["project_name"]
    project_dir = root / config.output_dir / project_name

    client = FeishuClient()
    agents = list(all_agents(root))
    pushed = 0
    for agent_dir in agents:
        fm, _ = load_agent_doc(agent_dir)
        agent_id = str(fm.get("id", agent_dir.name))
        title = str(fm.get("title", agent_id))
        output_path = latest_agent_output_path(project_dir, agent_id)

        if not output_path.exists():
            click.secho(f"  [{agent_id}] skipped — no output file", fg="yellow")
            continue

        output = output_path.read_text(encoding="utf-8")
        try:
            post_title, paragraphs = format_agent_for_post(agent_id, title, output)
            msg_id = client.send_post(chat_id, post_title, paragraphs)
            _store_message_link(root, msg_id, agent_id)
            pushed += 1
            click.echo(f"  [{agent_id}] pushed — {msg_id}")
        except FeishuError as e:
            click.secho(f"  [{agent_id}] FAILED: {e}", fg="red")

    click.secho(f"\nPushed {pushed}/{len(agents)} agents.", fg="green")


@feishu.command()
@click.option("--chat-id", required=True, help="Feishu group chat_id")
@click.option("--limit", default=20, help="Number of recent messages to fetch")
def feedback(chat_id: str, limit: int) -> None:
    """Fetch recent messages from a Feishu group and extract feedback."""
    client = FeishuClient()
    try:
        messages = client.list_messages(chat_id, limit=limit)
    except FeishuError as e:
        click.secho(str(e), fg="red")
        return

    if not messages:
        click.secho("No messages found in this chat.", fg="yellow")
        return

    feedbacks: list[Feedback] = []

    for msg in reversed(messages):
        role = "unknown"
        if msg.sender_name:
            role = msg.sender_name

        text = msg.content
        if not text:
            continue

        cmd, args = parse_bot_command(text)

        click.echo(f"[{msg.sender_name}] {cmd}: {text[:100]}")

        if cmd == "feedback":
            cleaned = parse_feedback_from_message(text)
            if cleaned:
                feedbacks.append(Feedback(
                    agent_id="unknown",
                    reviewer=role,
                    content=cleaned,
                ))

    if feedbacks:
        click.secho(f"\nCollected {len(feedbacks)} feedback item(s):", fg="cyan")
        for fb in feedbacks:
            click.echo(f"  [{fb.reviewer}] {fb.content[:200]}")
    else:
        click.echo("\nNo feedback found in recent messages.")


@feishu.command()
@click.option("--chat-id", required=True, help="Feishu group chat_id")
@click.pass_context
def status(ctx: click.Context, chat_id: str) -> None:
    """Push project status to a Feishu group."""
    root = Path.cwd()
    project_name: str = ctx.obj["project_name"]

    client = FeishuClient()
    try:
        title, paragraphs = build_status_post(root, project_name)
        msg_id = client.send_post(chat_id, title, paragraphs)
        click.secho(f"Status posted — {msg_id}", fg="green")
    except FeishuError as e:
        click.secho(str(e), fg="red")


@feishu.command()
@click.option("--chat-id", required=True, help="Feishu group chat_id")
def help_cmd(chat_id: str) -> None:
    """Push help message to a Feishu group."""
    client = FeishuClient()
    try:
        title, paragraphs = build_help_post()
        msg_id = client.send_post(chat_id, title, paragraphs)
        click.secho(f"Help posted — {msg_id}", fg="green")
    except FeishuError as e:
        click.secho(str(e), fg="red")


def _load_message_map(root: Path) -> dict[str, str]:
    """Load message_id -> agent_id mapping."""
    map_path = root / ".geniusforge" / "message-map.json"
    if map_path.exists():
        import json
        return json.loads(map_path.read_text(encoding="utf-8"))
    return {}


def _save_message_map(root: Path, mapping: dict[str, str]) -> None:
    """Save message_id -> agent_id mapping."""
    import json
    map_dir = root / ".geniusforge"
    map_dir.mkdir(parents=True, exist_ok=True)
    (map_dir / "message-map.json").write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")


def _store_message_link(root: Path, message_id: str, agent_id: str) -> None:
    """Record that a message is associated with a specific agent."""
    mapping = _load_message_map(root)
    mapping[message_id] = agent_id
    # Keep only last 100 entries
    if len(mapping) > 100:
        keys = list(mapping.keys())[-100:]
        mapping = {k: mapping[k] for k in keys}
    _save_message_map(root, mapping)


def _lookup_agent_for_message(root: Path, root_id: str | None) -> str | None:
    """Find which agent a message reply is about."""
    if not root_id:
        return None
    mapping = _load_message_map(root)
    return mapping.get(root_id)


@feishu.command()
@click.option("--chat-id", default=None, help="Feishu group chat_id (omit to auto-discover all chats)")
@click.option("--interval", default=10, help="Poll interval in seconds")
@click.pass_context
def listen(ctx: click.Context, chat_id: str | None, interval: int) -> None:
    """Monitor Feishu groups and respond to bot commands.

    If --chat-id is omitted, auto-discovers all chats the bot is in
    and monitors all of them simultaneously. Newly added groups are
    picked up automatically every 60 seconds.

    Workflow:
      新建项目 → 输入项目名称 → 输入客户需求 → PM 生成方案 →
      审阅反馈 → 确认通过 → 自动运行全部下游 Agent

    Press Ctrl+C to stop.
    """
    import time

    root = Path.cwd()
    config = load_config(root)
    default_project: str = ctx.obj["project_name"]
    client = FeishuClient()

    # ── Discover chats ──
    if chat_id:
        chat_ids = [chat_id]
        click.echo(f"Monitoring chat: {chat_id}")
    else:
        try:
            all_chats = client.list_chats()
            chat_ids = [c["chat_id"] for c in all_chats]
            if not chat_ids:
                click.secho(
                    "No chats found. Add the bot to a Feishu group first.",
                    fg="yellow",
                )
                return
            click.echo(f"Auto-discovered {len(chat_ids)} chat(s):")
            for c in all_chats:
                click.echo(f"  {c['chat_id']} — {c['name']}")
        except FeishuError as e:
            click.secho(str(e), fg="red")
            return

    # ── Load persisted project-creation states ──
    states = _load_project_states(root)

    # ── Per-chat state ──
    last_seen: dict[str, set[str]] = {}
    _last_chat_refresh: float = time.time()

    # Seed with existing message IDs for each chat
    for cid in chat_ids:
        try:
            existing = client.list_messages(cid, limit=10)
            last_seen[cid] = {m.message_id for m in existing}
        except FeishuError:
            last_seen[cid] = set()

    click.secho(
        f"Listening on {len(chat_ids)} chat(s) (poll every {interval}s). Ctrl+C to stop.",
        fg="cyan",
    )

    def _refresh_chats() -> list[str]:
        """Re-discover chats; return updated list. New chats seed last_seen."""
        nonlocal chat_ids
        try:
            fresh = client.list_chats()
            fresh_ids = [c["chat_id"] for c in fresh]
            for cid in fresh_ids:
                if cid not in last_seen:
                    last_seen[cid] = set()
                    click.echo(f"  → discovered new chat: {cid} — "
                               f"{next((c['name'] for c in fresh if c['chat_id'] == cid), '')}")
            return fresh_ids
        except FeishuError:
            return chat_ids

    def _cap_seen(s: set[str], max_size: int = 200) -> set[str]:
        """Keep only the most recent entries to bound memory."""
        if len(s) > max_size:
            return set(list(s)[-max_size:])
        return s

    try:
        while True:
            # ── Periodic chat list refresh (every 60s) ──
            now = time.time()
            if not chat_id and now - _last_chat_refresh > 60:
                chat_ids = _refresh_chats()
                _last_chat_refresh = now

            for cid in chat_ids:
                try:
                    messages = client.list_messages(cid, limit=10)
                except FeishuError:
                    continue

                seen = last_seen.get(cid, set())
                for msg in messages:
                    if msg.message_id in seen:
                        continue
                    seen.add(msg.message_id)

                    # Skip bot's own messages and file uploads
                    if msg.sender_type == "app":
                        continue

                    text = msg.content
                    if not text:
                        continue
                    # Skip JSON payloads from file messages
                    if text.startswith("{"):
                        continue

                    cmd, args = parse_bot_command(text)
                    role = msg.sender_name or "工程师"

                    # ── Project-creation state machine ──
                    st = states.get(cid)
                    if st is not None and st.phase != "idle":
                        click.echo(f"\n[{cid[:8]}][{role}] [phase={st.phase}] {text[:120]}")
                        _handle_state_machine(
                            client, cid, root, config, states, st, msg, text, role,
                        )
                        continue

                    click.echo(f"\n[{cid[:8]}][{role}] {cmd}: {text[:120]}")

                    # ── Global commands ──

                    if cmd == "new_project":
                        client.send_text(cid, "🚀 收到！请输入新项目名称（例如：手机屏幕检测）：")
                        states[cid] = ProjectState(phase="collecting_name")
                        _save_project_states(root, states)
                        click.echo("  → entering new project flow (collecting_name)")

                    elif cmd == "status":
                        title, paras = build_status_post(root, default_project)
                        client.send_post(cid, title, paras)
                        click.echo("  → sent status")

                    elif cmd == "help":
                        title, paras = build_help_post()
                        client.send_post(cid, title, paras)
                        click.echo("  → sent help")

                    elif cmd == "view":
                        agent_id = _resolve_agent_keyword(args)
                        if agent_id:
                            msg_id = _push_agent_output(client, cid, agent_id, project_name=default_project)
                            if msg_id:
                                _store_message_link(root, msg_id, agent_id)
                            click.echo(f"  → pushed {agent_id}")
                        else:
                            client.send_text(cid, f"未找到匹配的 Agent: {args}")

                    elif cmd == "rerun":
                        agent_id = _resolve_agent_keyword(args)
                        if agent_id:
                            client.send_text(cid, f"正在重新生成 {agent_id} 方案，请稍候...")
                            _rerun_agent_and_push(client, cid, root, agent_id, feedback="", project_name=default_project)
                            click.echo(f"  → reran {agent_id}")
                        else:
                            client.send_text(cid, f"未找到匹配的 Agent: {args}")

                    elif cmd == "approve":
                        target_agent = _lookup_agent_for_message(root, msg.root_id)
                        if target_agent:
                            client.send_text(cid, f"✅ {role} 确认通过 {target_agent} 方案！")
                        else:
                            client.send_text(cid, f"✅ 已收到 {role} 的确认。方案通过！")
                        click.echo(f"  → approved by {role}")

                    elif cmd == "feedback":
                        cleaned = parse_feedback_from_message(text)
                        if not cleaned:
                            continue
                        target_agent = _lookup_agent_for_message(root, msg.root_id)
                        if not target_agent:
                            target_agent = _resolve_agent_keyword_from_text(cleaned)
                        if target_agent:
                            client.send_text(cid, f"收到 {role} 对 {target_agent} 方案的反馈，正在重新生成方案，请稍候...")
                            _rerun_agent_and_push(client, cid, root, target_agent, feedback=cleaned)
                            click.echo(f"  → rerunning {target_agent} with feedback")
                        else:
                            client.send_text(
                                cid,
                                f"✅ 已收到 {role} 的反馈：{cleaned[:200]}。\n\n"
                                f"请明确是针对哪个 Agent 的方案？回复格式：**Agent名称 + 反馈内容**\n"
                                f"例如：「光学 环形LED亮度不够」或「03-optics 需要改偏振方案」"
                            )
                            click.echo(f"  → feedback saved (unmatched agent): {cleaned[:100]}")

                # Cap seen set size per chat
                last_seen[cid] = _cap_seen(seen)

            time.sleep(interval)

    except KeyboardInterrupt:
        click.secho("\nStopped listening.", fg="yellow")


# ── State machine handler ───────────────────────────────────────────────────

def _handle_state_machine(
    client: FeishuClient,
    chat_id: str,
    root: Path,
    config,
    states: dict[str, ProjectState],
    st: ProjectState,
    msg: ChatMessage,
    text: str,
    role: str,
) -> None:
    """Process a message in the context of the project-creation state machine."""

    if st.phase == "collecting_name":
        # User provides project name — strip @mentions first
        project_name = re.sub(r"@\S+", "", text).strip()[:50]
        # Sanitize: replace spaces with hyphens, remove special chars
        project_name = "".join(c if c.isalnum() or c in ".-_" else "-" for c in project_name)
        if not project_name or project_name == "-":
            client.send_text(chat_id, "项目名称无效，请输入有效名称（如：手机屏幕检测）：")
            return

        st.project_name = project_name
        project_dir = root / config.output_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        client.send_text(
            chat_id,
            f"✅ 项目「{project_name}」已创建！\n\n"
            f"请描述客户需求（如：检测分辨率、节拍时间、缺陷类型等）：\n"
            f"（需求越详细，PM 方案越精准）"
        )
        st.phase = "collecting_reqs"
        _save_project_states(root, states)
        click.echo(f"  → project '{project_name}' created, waiting for requirements")

    elif st.phase == "collecting_reqs":
        # User provides requirements — strip @mentions
        st.requirements = re.sub(r"@\S+", "", text).strip()
        client.send_text(chat_id, f"📝 已收到需求，正在生成「{st.project_name}」PM 技术方案，请稍候...")

        # Write requirements.md
        project_dir = root / config.output_dir / st.project_name
        (project_dir / "requirements.md").write_text(st.requirements, encoding="utf-8")

        # Run PM agent (01-pm) — the only agent that runs in this phase
        from core.engine import PipelineEngine
        engine = PipelineEngine(root, config)
        result = engine.run_single(st.project_name, "01-pm")

        if result.success:
            # Upload engine-generated .docx directly
            agent_dir = root / "agents" / "01-pm"
            fm, _ = load_agent_doc(agent_dir)
            title = str(fm.get("title", "01-pm"))
            docx_path = project_dir / "01-pm-方案.docx"
            file_key = client.upload_file(docx_path)
            file_msg_id = client.send_file(chat_id, file_key)
            st.pm_message_id = file_msg_id
            _store_message_link(root, file_msg_id, "01-pm")

            client.send_text(
                chat_id,
                f"☝️ 以上是 PM 技术方案（{result.tokens_used} tokens, {result.duration_ms/1000:.1f}s）\n\n"
                f"请审阅 PM 方案。\n"
                f"• 回复 **修改建议** 可让 PM 重新生成\n"
                f"• 回复 ✅ 确认通过后，将自动运行全部下游 Agent（机械/光学/运动/算法/评审）"
            )
            st.phase = "pm_approved"  # ready to trigger rest on approval
            _save_project_states(root, states)
            click.echo(f"  → PM done for '{st.project_name}', awaiting approval")
        else:
            client.send_text(chat_id, f"❌ PM Agent 生成失败：{result.error}")
            st.phase = "idle"  # reset so user can retry
            _save_project_states(root, states)

    elif st.phase == "pm_approved":
        # Check if this is an approval or feedback on PM
        cmd, args = parse_bot_command(text)

        if cmd == "approve":
            client.send_text(chat_id, f"✅ PM 方案确认通过！正在运行全部下游 Agent：机械结构 → 光学 → 运动控制 → 算法 → 整机评审...")

            from core.engine import PipelineEngine
            engine = PipelineEngine(root, config)
            eng_result = engine.run_all(st.project_name, from_agent="02-mechanical")

            if eng_result.all_success:
                # Push all outputs
                pushed_count, failed_pushes = _push_all_agent_outputs(
                    client,
                    chat_id,
                    root,
                    config,
                    st.project_name,
                )
                push_summary = f"已推送 {pushed_count} 个方案。"
                if failed_pushes:
                    push_summary += f" 推送失败/缺失：{', '.join(failed_pushes)}。"
                client.send_text(
                    chat_id,
                    f"🎉 项目「{st.project_name}」全部方案已生成！\n"
                    f"{eng_result.summary}\n\n"
                    f"{push_summary}\n"
                    f"可回复 **状态** 查看各 Agent 方案详情。"
                )
            else:
                client.send_text(
                    chat_id,
                    f"⚠️ 部分 Agent 生成失败：{', '.join(eng_result.failed_agents)}\n{eng_result.summary}"
                )
            st.phase = "done"
            _save_project_states(root, states)
            click.echo(f"  → project '{st.project_name}' complete")

        elif cmd == "feedback":
            cleaned = parse_feedback_from_message(text)
            if cleaned:
                client.send_text(chat_id, f"📝 收到 PM 方案反馈，正在重新生成...")
                _rerun_agent_and_push(
                    client, chat_id, root, "01-pm", feedback=cleaned,
                    project_name=st.project_name,
                )
                # Stay in pm_approved phase — user can give more feedback or approve
                click.echo(f"  → PM rerunning with feedback")
        else:
            # Not an approve or feedback — treat as general message
            client.send_text(chat_id, f"当前 PM 方案待审阅。请回复 ✅ 确认通过，或回复修改建议。")

    elif st.phase == "done":
        cmd, args = parse_bot_command(text)
        if cmd == "new_project":
            states[chat_id] = ProjectState(phase="collecting_name")
            _save_project_states(root, states)
            client.send_text(chat_id, "🚀 收到！请输入新项目名称（例如：手机屏幕检测）：")
            click.echo("  → reset from done, entering new project flow")
        elif cmd == "status":
            title, paras = build_status_post(root, st.project_name)
            client.send_post(chat_id, title, paras)
            click.echo("  → sent status")
        elif cmd == "help":
            title, paras = build_help_post()
            client.send_post(chat_id, title, paras)
            click.echo("  → sent help")
        elif cmd == "view":
            agent_id = _resolve_agent_keyword(args)
            if agent_id:
                msg_id = _push_agent_output(client, chat_id, agent_id, project_name=st.project_name)
                if msg_id:
                    _store_message_link(root, msg_id, agent_id)
                click.echo(f"  → pushed {agent_id}")
            else:
                client.send_text(chat_id, f"未找到匹配的 Agent: {args}")
        elif cmd == "rerun":
            agent_id = _resolve_agent_keyword(args)
            if agent_id:
                client.send_text(chat_id, f"正在重新生成 {agent_id} 方案，请稍候...")
                _rerun_agent_and_push(client, chat_id, root, agent_id, feedback="", project_name=st.project_name)
                click.echo(f"  → reran {agent_id}")
            else:
                client.send_text(chat_id, f"未找到匹配的 Agent: {args}")
        else:
            client.send_text(
                chat_id,
                f"上一个项目「{st.project_name}」已完成。回复 **新建项目** 开始新流程，"
                f"或回复 **状态** / **查看 <Agent>** 回顾方案。"
            )


def _push_all_agent_outputs(
    client: FeishuClient, chat_id: str, root: Path, config, project_name: str,
) -> tuple[int, list[str]]:
    """Push all agent outputs as Word documents for a completed project."""
    project_dir = root / config.output_dir / project_name
    pushed = 0
    failed: list[str] = []
    for agent_dir in all_agents(root):
        fm, _ = load_agent_doc(agent_dir)
        agent_id = str(fm.get("id", agent_dir.name))
        docx_path = latest_docx_output_path(project_dir, agent_id)
        if not docx_path.exists():
            failed.append(agent_id)
            click.secho(f"  [{agent_id}] skipped — no output file", fg="yellow")
            continue
        try:
            file_key = client.upload_file(docx_path)
            file_msg_id = client.send_file(chat_id, file_key)
            _store_message_link(root, file_msg_id, agent_id)
        except FeishuError as e:
            failed.append(agent_id)
            click.secho(f"  [{agent_id}] upload FAILED: {e}", fg="red")
            continue
        pushed += 1
        click.echo(f"  [{agent_id}] pushed")
    return pushed, failed


def _resolve_agent_keyword_from_text(text: str) -> str | None:
    """Try to extract agent keyword from the beginning of feedback text."""
    root = Path.cwd()
    text_lower = text.lower()

    # Check for agent IDs like "01-pm", "03-optics"
    for agent_dir in all_agents(root):
        fm, _ = load_agent_doc(agent_dir)
        aid = str(fm.get("id", ""))
        if aid.lower() in text_lower:
            return aid

    # Check for Chinese names
    keywords = {
        "产品经理": "01-pm", "pm": "01-pm",
        "机械": "02-mechanical", "mechanical": "02-mechanical",
        "光学": "03-optics", "optics": "03-optics",
        "运动控制": "04-motion", "运动": "04-motion", "motion": "04-motion",
        "算法": "05-algorithm", "algorithm": "05-algorithm",
        "整机评审": "06-review", "评审": "06-review", "review": "06-review",
    }
    for kw, aid in keywords.items():
        if kw.lower() in text_lower:
            return aid
    return None


def _rerun_agent_and_push(
    client: FeishuClient, chat_id: str, root: Path, agent_id: str, feedback: str,
    project_name: str = "pic",
) -> None:
    """Re-run an agent with feedback and push the new output."""
    from core.engine import PipelineEngine

    config = load_config(root)
    engine = PipelineEngine(root, config)

    result = engine.run_single(project_name, agent_id, feedback=feedback)

    if result.success:
        project_dir = root / config.output_dir / project_name
        if result.output_path is not None:
            docx_path = result.output_path.with_suffix(".docx")
        else:
            docx_path = latest_docx_output_path(project_dir, agent_id)

        file_key = client.upload_file(docx_path)
        file_msg_id = client.send_file(chat_id, file_key)
        _store_message_link(root, file_msg_id, agent_id)

        click.echo(f"  [{agent_id}] regenerated — {result.tokens_used} tokens")
    else:
        client.send_text(chat_id, f"❌ {agent_id} 重新生成失败：{result.error}")
        click.echo(f"  [{agent_id}] FAILED: {result.error}")


def _resolve_agent_keyword(keyword: str) -> str | None:
    """Resolve a Chinese/English keyword to an agent ID."""
    root = Path.cwd()
    keyword_lower = keyword.strip().lower()

    # Direct match: agent ID like "01-pm", "03-optics"
    for agent_dir in all_agents(root):
        fm, _ = load_agent_doc(agent_dir)
        aid = str(fm.get("id", ""))
        if keyword_lower == aid.lower():
            return aid

    # Fuzzy match: Chinese name like "光学", "机械", "产品经理"
    mapping: dict[str, str] = {}
    for agent_dir in all_agents(root):
        fm, _ = load_agent_doc(agent_dir)
        aid = str(fm.get("id", ""))
        title = str(fm.get("title", ""))
        mapping[title] = aid
        # Also add short parts
        for part in title.replace("Agent", "").split():
            mapping[part] = aid

    for title_part, aid in mapping.items():
        if keyword_lower in title_part.lower():
            return aid

    return None


@feishu.command()
@click.option("--chat-id", required=True, help="Feishu group chat_id")
@click.option("--output-dir", default=None, help="Output directory for .docx files (default: .geniusforge/docx/)")
@click.pass_context
def export_all(ctx: click.Context, chat_id: str, output_dir: str | None) -> None:
    """Export all agent outputs as Word documents and upload to Feishu group."""
    root = Path.cwd()
    config = load_config(root)
    project_name: str = ctx.obj["project_name"]
    project_dir = root / config.output_dir / project_name

    client = FeishuClient()
    agents = list(all_agents(root))

    exported = 0
    for agent_dir in agents:
        fm, _ = load_agent_doc(agent_dir)
        agent_id = str(fm.get("id", agent_dir.name))
        docx_path = latest_docx_output_path(project_dir, agent_id)

        if not docx_path.exists():
            click.secho(f"  [{agent_id}] skipped — no output file", fg="yellow")
            continue

        # Upload and send
        try:
            file_key = client.upload_file(docx_path)
            msg_id = client.send_file(chat_id, file_key)
            click.echo(f"  [{agent_id}] uploaded → message_id: {msg_id}")
            exported += 1
        except FeishuError as e:
            click.secho(f"  [{agent_id}] upload FAILED: {e}", fg="red")

    click.secho(f"\nExported & uploaded {exported}/{len(agents)} agents.", fg="green")


@feishu.command()
@click.option("--chat-id", required=True, help="Feishu group chat_id")
@click.argument("agent_id")
@click.pass_context
def export_push(ctx: click.Context, chat_id: str, agent_id: str) -> None:
    """Export a single agent output as Word and upload to Feishu."""
    root = Path.cwd()
    config = load_config(root)
    project_name: str = ctx.obj["project_name"]
    project_dir = root / config.output_dir / project_name

    docx_path = latest_docx_output_path(project_dir, agent_id)
    if not docx_path.exists():
        click.secho(f"File not found: {docx_path}", fg="red")
        return

    client = FeishuClient()
    try:
        file_key = client.upload_file(docx_path)
        msg_id = client.send_file(chat_id, file_key)
        click.secho(f"Uploaded {agent_id} → message_id: {msg_id}", fg="green")
    except FeishuError as e:
        click.secho(str(e), fg="red")


def _push_agent_output(client: FeishuClient, chat_id: str, agent_id: str, project_name: str = "pic") -> str | None:
    root = Path.cwd()
    config = load_config(root)
    project_dir = root / config.output_dir / project_name
    docx_path = latest_docx_output_path(project_dir, agent_id)
    if not docx_path.exists():
        client.send_text(chat_id, f"Agent {agent_id} 方案文件不存在，请先生成。")
        return None

    file_key = client.upload_file(docx_path)
    return client.send_file(chat_id, file_key)
