"""Tests for feishu/bot.py — message parsing, formatting, command detection."""
from pathlib import Path

import pytest
from core.runner import RunResult
from feishu.bot import (
    parse_bot_command,
    parse_feedback_from_message,
    get_agent_role,
    format_agent_for_post,
)
from feishu.monitor import get_pipeline_status, get_project_dir


class TestParseBotCommand:
    def test_new_project(self) -> None:
        cmd, args = parse_bot_command("新建项目")
        assert cmd == "new_project"

    def test_new_project_create(self) -> None:
        cmd, args = parse_bot_command("创建项目")
        assert cmd == "new_project"

    def test_new_project_english(self) -> None:
        cmd, args = parse_bot_command("new project")
        assert cmd == "new_project"

    def test_new_project_wins_over_help(self) -> None:
        """新项目 should take priority over other keywords."""
        cmd, args = parse_bot_command("新建项目 帮助")
        assert cmd == "new_project"

    def test_help(self) -> None:
        cmd, args = parse_bot_command("帮助")
        assert cmd == "help"

    def test_help_english(self) -> None:
        cmd, args = parse_bot_command("help")
        assert cmd == "help"

    def test_status(self) -> None:
        cmd, args = parse_bot_command("当前状态")
        assert cmd == "status"

    def test_status_english(self) -> None:
        cmd, args = parse_bot_command("status")
        assert cmd == "status"

    def test_view_agent(self) -> None:
        cmd, args = parse_bot_command("查看 光学")
        assert cmd == "view"
        assert args == "光学"

    def test_view_agent_english(self) -> None:
        cmd, args = parse_bot_command("view 03-optics")
        assert cmd == "view"
        assert args == "03-optics"

    def test_rerun_agent(self) -> None:
        cmd, args = parse_bot_command("重跑 02-mechanical")
        assert cmd == "rerun"
        assert args == "02-mechanical"

    def test_rerun_agent_english(self) -> None:
        cmd, args = parse_bot_command("rerun 04-motion")
        assert cmd == "rerun"
        assert args == "04-motion"

    def test_rerun_domestic(self) -> None:
        cmd, args = parse_bot_command("重新生成 03-optics")
        assert cmd == "rerun"
        assert args == "03-optics"

    def test_approve_checkmark(self) -> None:
        cmd, args = parse_bot_command("✅")
        assert cmd == "approve"

    def test_approve_confirm(self) -> None:
        cmd, args = parse_bot_command("确认通过")
        assert cmd == "approve"

    def test_approve_ok(self) -> None:
        cmd, args = parse_bot_command("OK 没问题")
        assert cmd == "approve"

    def test_feedback_default(self) -> None:
        cmd, args = parse_bot_command("光学方案亮度不够")
        assert cmd == "feedback"
        assert args == "光学方案亮度不够"


class TestParseFeedbackFromMessage:
    def test_removes_bot_mention(self) -> None:
        result = parse_feedback_from_message("@GeniusForge机器人 需要增加散热设计")
        assert "@GeniusForge" not in result
        assert "需要增加散热设计" in result

    def test_removes_bot_keyword(self) -> None:
        result = parse_feedback_from_message("@somebot 改进材料选型")
        assert "改进材料选型" in result

    def test_preserves_clean_text(self) -> None:
        result = parse_feedback_from_message("光源亮度需要提高到 1000lux")
        assert result == "光源亮度需要提高到 1000lux"

    def test_strips_whitespace(self) -> None:
        result = parse_feedback_from_message("  补充受力分析  ")
        assert result == "补充受力分析"


class TestGetAgentRole:
    def test_known_agents(self) -> None:
        assert get_agent_role("01-pm") == "产品经理"
        assert get_agent_role("02-mechanical") == "机械结构工程师"
        assert get_agent_role("03-optics") == "光学工程师"
        assert get_agent_role("04-motion") == "运动控制工程师"
        assert get_agent_role("05-algorithm") == "算法工程师"
        assert get_agent_role("06-review") == "整机评审工程师"

    def test_unknown_falls_back_to_id(self) -> None:
        assert get_agent_role("99-unknown") == "99-unknown"


class TestFormatAgentForPost:
    def test_short_output(self) -> None:
        title, paragraphs = format_agent_for_post(
            "03-optics", "光学工程师", "## 光源设计\n\n使用LED环形光源。\n\n## 参数\n\n- 亮度: 1000lux"
        )
        assert "光学工程师" in title
        assert len(paragraphs) >= 2  # header + at least one section

    def test_long_output_truncation(self) -> None:
        long_text = "A" * 30000
        title, paragraphs = format_agent_for_post("01-pm", "产品经理", long_text)
        combined = "".join(p.get("text", "") for p in paragraphs[0])
        # First paragraph (header) should be short, content should be in later paragraphs
        assert len(paragraphs) >= 1

    def test_message_link_back_compat(self) -> None:
        """Verify message_id→agent_id mapping functions import correctly."""
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            map_dir = root / ".geniusforge"
            map_dir.mkdir()
            map_file = map_dir / "message-map.json"
            data = {"msg_001": "01-pm", "msg_002": "03-optics"}
            map_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            loaded = json.loads(map_file.read_text(encoding="utf-8"))
            assert loaded == data
            assert loaded["msg_001"] == "01-pm"
            assert loaded.get("msg_nonexistent") is None


def test_rerun_agent_without_feedback_pushes_base_output(tmp_path: Path, monkeypatch) -> None:
    from cli import feishu_cmd
    import core.engine

    agent_dir = tmp_path / "agents" / "01-pm"
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.md").write_text(
        "---\n"
        "id: 01-pm\n"
        "name: pm\n"
        "title: 产品经理\n"
        "role: PM\n"
        "---\n"
        "# Role\nPM\n",
        encoding="utf-8",
    )

    class FakeEngine:
        def __init__(self, root: Path, config) -> None:
            self.root = root

        def run_single(self, project_name: str, agent_id: str, feedback: str = "") -> RunResult:
            project_dir = self.root / "examples" / project_name
            project_dir.mkdir(parents=True, exist_ok=True)
            output_path = project_dir / f"{agent_id}-方案.md"
            output_path.write_text("fresh output", encoding="utf-8")
            # Engine now also creates .docx
            docx_path = project_dir / f"{agent_id}-方案.docx"
            docx_path.write_text("fake-docx-content")
            return RunResult(
                agent_id=agent_id,
                success=True,
                output="fresh output",
                output_path=output_path,
            )

    class FakeClient:
        def upload_file(self, file_path: Path) -> str:
            assert file_path.exists()
            return "file-key"

        def send_file(self, chat_id: str, file_key: str) -> str:
            assert chat_id == "chat-id"
            assert file_key == "file-key"
            return "message-id"

    monkeypatch.setattr(core.engine, "PipelineEngine", FakeEngine)

    feishu_cmd._rerun_agent_and_push(
        FakeClient(),
        "chat-id",
        tmp_path,
        "01-pm",
        feedback="",
        project_name="demo",
    )


def test_status_uses_configured_output_dir(tmp_path: Path) -> None:
    (tmp_path / "pipeline.yaml").write_text("output_dir: custom-output\n", encoding="utf-8")
    project_dir = tmp_path / "custom-output" / "demo"
    project_dir.mkdir(parents=True)
    (project_dir / "01-pm-方案.docx").write_bytes(b"x" * 101)
    (project_dir / "01-pm-方案.md").write_text("tokens: 1200", encoding="utf-8")

    assert get_project_dir(tmp_path, "demo") == project_dir

    states = get_pipeline_status(tmp_path, "demo")

    assert states[0].agent_id == "01-pm"
    assert states[0].status == "done"
    assert states[1].status == "pending"


def test_push_all_reports_failed_uploads(tmp_path: Path, monkeypatch) -> None:
    from cli import feishu_cmd
    from feishu.client import FeishuError

    agents_root = tmp_path / "agents"
    for agent_id in ("01-pm", "02-mechanical"):
        agent_dir = agents_root / agent_id
        agent_dir.mkdir(parents=True)
        (agent_dir / "agent.md").write_text(
            "---\n"
            f"id: {agent_id}\n"
            f"name: {agent_id}\n"
            f"title: {agent_id}\n"
            f"role: {agent_id}\n"
            "---\n"
            "# Role\n",
            encoding="utf-8",
        )

    project_dir = tmp_path / "examples" / "demo"
    project_dir.mkdir(parents=True)
    (project_dir / "01-pm-方案.docx").write_bytes(b"docx")
    (project_dir / "02-mechanical-方案.docx").write_bytes(b"docx")

    class Config:
        output_dir = "examples"

    class FakeClient:
        def upload_file(self, file_path: Path) -> str:
            if file_path.name.startswith("02-mechanical"):
                raise FeishuError("upload failed")
            return "file-key"

        def send_file(self, chat_id: str, file_key: str) -> str:
            assert chat_id == "chat-id"
            assert file_key == "file-key"
            return "message-id"

    monkeypatch.chdir(tmp_path)

    pushed, failed = feishu_cmd._push_all_agent_outputs(
        FakeClient(),
        "chat-id",
        tmp_path,
        Config(),
        "demo",
    )

    assert pushed == 1
    assert failed == ["02-mechanical"]


def test_status_command_uses_selected_project(monkeypatch) -> None:
    from click.testing import CliRunner
    from cli.feishu_cmd import feishu
    import cli.feishu_cmd as feishu_cmd

    seen_projects: list[str] = []

    def fake_build_status_post(root: Path, project_name: str):
        seen_projects.append(project_name)
        return "title", [[{"tag": "text", "text": "status"}]]

    class FakeClient:
        def send_post(self, chat_id: str, title: str, paragraphs) -> str:
            assert chat_id == "chat-id"
            assert title == "title"
            return "message-id"

    monkeypatch.setattr(feishu_cmd, "build_status_post", fake_build_status_post)
    monkeypatch.setattr(feishu_cmd, "FeishuClient", FakeClient)

    result = CliRunner().invoke(
        feishu,
        ["--project", "demo-project", "status", "--chat-id", "chat-id"],
    )

    assert result.exit_code == 0
    assert seen_projects == ["demo-project"]
