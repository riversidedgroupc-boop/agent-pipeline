"""Monitor data aggregation for Feishu status display.

Reads pipeline state from filesystem (output files, run-status JSONs),
estimates token counts, and calculates costs for Feishu post rendering.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

AGENT_IDS = [
    "01-pm", "02-mechanical", "03-optics",
    "04-motion", "05-algorithm", "06-review",
]

AGENT_LABELS: dict[str, str] = {
    "01-pm": "产品经理",
    "02-mechanical": "机械结构",
    "03-optics": "光学",
    "04-motion": "运动控制",
    "05-algorithm": "算法",
    "06-review": "整机评审",
}

# DeepSeek v4 pricing (per 1M tokens, USD)
PRICE_OUTPUT = 1.10
USD_TO_CNY = 7.25


class AgentState:
    """Snapshot of one agent's pipeline state."""

    def __init__(
        self,
        agent_id: str,
        status: str,  # done | running | pending | blocked | failed
        tokens_used: int = 0,
        output_size_kb: float = 0.0,
        cost_cny: float = 0.0,
        error: str = "",
    ) -> None:
        self.agent_id = agent_id
        self.status = status
        self.tokens_used = tokens_used
        self.output_size_kb = output_size_kb
        self.cost_cny = cost_cny
        self.error = error

    @property
    def label(self) -> str:
        return AGENT_LABELS.get(self.agent_id, self.agent_id)

    @property
    def icon(self) -> str:
        return {
            "done": "✅",
            "running": "⏳",
            "failed": "❌",
            "blocked": "🔒",
            "pending": "⬜",
        }.get(self.status, "⬜")

    @property
    def status_text(self) -> str:
        return {
            "done": "完成",
            "running": "运行中",
            "failed": "失败",
            "blocked": "阻塞",
            "pending": "排队中",
        }.get(self.status, self.status)


def _load_config(root: Path) -> dict[str, Any]:
    path = root / "pipeline.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def get_project_dir(root: Path, project_name: str) -> Path:
    """Return the configured output directory for a project."""
    config = _load_config(root)
    output_dir = str(config.get("output_dir", "examples"))
    return root / output_dir / project_name


def _count_tokens_in_output(filepath: Path) -> int:
    """Estimate tokens from output file. Looks for LLM-reported tokens first, then falls back to char-count estimation."""
    if not filepath.exists():
        return 0
    text = filepath.read_text(encoding="utf-8")
    m = re.search(r"(?:tokens|Tokens)[:\s]*([\d,]+)", text)
    if m:
        return int(m.group(1).replace(",", ""))
    # Rough: ~3 chars/token for Chinese+code mix
    return max(1, len(text) // 3)


def _tokens_to_cost(tokens: int) -> float:
    return tokens / 1_000_000 * PRICE_OUTPUT * USD_TO_CNY


def get_pipeline_status(root: Path, project_name: str) -> list[AgentState]:
    """Return per-agent status for a project."""
    project_dir = get_project_dir(root, project_name)
    run_status_path = root / ".geniusforge" / f"run-status-{project_name}.json"
    run_status: dict[str, str] = {}
    if run_status_path.exists():
        run_status = json.loads(run_status_path.read_text(encoding="utf-8"))

    result: list[AgentState] = []
    for aid in AGENT_IDS:
        docx_path = project_dir / f"{aid}-方案.docx"
        md_path = project_dir / f"{aid}-方案.md"
        status = run_status.get(aid, "pending")

        if docx_path.exists() and docx_path.stat().st_size > 100:
            if status not in ("running", "failed"):
                status = "done"
        elif status == "running":
            pass
        elif status == "failed":
            pass
        else:
            # Check if blocked by upstream
            upstream_ids = AGENT_IDS[: AGENT_IDS.index(aid)]
            all_up_done = all(
                (project_dir / f"{u}-方案.docx").exists() for u in upstream_ids
            )
            if upstream_ids and not all_up_done:
                status = "blocked"
            else:
                status = "pending"

        tokens = _count_tokens_in_output(md_path) if status == "done" else 0
        size_kb = docx_path.stat().st_size / 1024 if docx_path.exists() else 0.0
        cost = _tokens_to_cost(tokens) if tokens else 0.0

        result.append(AgentState(
            agent_id=aid,
            status=status,
            tokens_used=tokens,
            output_size_kb=size_kb,
            cost_cny=cost,
        ))

    return result


def get_model_config(root: Path) -> dict[str, str]:
    config = _load_config(root)
    model = config.get("model", {})
    return {
        "model": model.get("model", "deepseek-v4-pro"),
        "retry": str(config.get("retry", 2)),
        "max_tokens": str(model.get("max_tokens", 8192)),
    }
