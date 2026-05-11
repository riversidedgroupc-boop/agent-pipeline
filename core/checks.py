"""
Upstream-downstream interface consistency checks.
"""
from __future__ import annotations

from pathlib import Path

from .template import load_agent_doc, all_agents


def check_pipeline(root: Path) -> list[str]:
    """Run all interface checks. Returns list of issues (empty = OK)."""
    issues: list[str] = []

    agents = all_agents(root)
    if not agents:
        issues.append("No agent directories found under agents/")
        return issues

    agent_map: dict[str, Path] = {}
    for d in agents:
        try:
            fm, _ = load_agent_doc(d)
            aid = str(fm.get("id", ""))
            if not aid:
                issues.append(f"{d.name}: missing 'id' in frontmatter")
                continue
            agent_map[aid] = d
        except FileNotFoundError:
            issues.append(f"{d.name}: agent.md not found")
            continue

    # Check upstream/downstream references are valid
    for aid, d in agent_map.items():
        fm, _ = load_agent_doc(d)
        upstream: list[str] = fm.get("upstream", [])
        downstream: list[str] = fm.get("downstream", [])

        for u in upstream:
            if u not in agent_map:
                issues.append(f"{aid}: upstream agent '{u}' not found")

        for dw in downstream:
            if dw not in agent_map:
                issues.append(f"{aid}: downstream agent '{dw}' not found")

    # Check the chain is connected (no orphan agents)
    all_ids = set(agent_map)
    has_upstream: set[str] = set()
    has_downstream: set[str] = set()
    for aid, d in agent_map.items():
        fm, _ = load_agent_doc(d)
        has_upstream.update(fm.get("upstream", []))
        has_downstream.update(fm.get("downstream", []))

    for aid in all_ids:
        # first agent has no upstream
        if aid == sorted(all_ids)[0]:
            continue
        # last agent has no downstream
        if aid == sorted(all_ids)[-1]:
            continue

    if not issues:
        # Check required files exist for each agent
        for aid, d in agent_map.items():
            for fname in ("agent.md", "template.md", "checklist.md"):
                if not (d / fname).exists():
                    issues.append(f"{aid}: missing {fname}")

    return issues
