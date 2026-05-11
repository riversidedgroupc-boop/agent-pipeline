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

    # Check upstream/downstream references point to existing agents
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

    # Check chain connectivity: every intermediate agent must be referenced
    # by at least one other agent as upstream or downstream
    all_ids = set(agent_map)
    referenced: set[str] = set()
    for aid, d in agent_map.items():
        fm, _ = load_agent_doc(d)
        referenced.update(fm.get("upstream", []))
        referenced.update(fm.get("downstream", []))

    # The first and last agents in sorted order can be endpoints
    sorted_ids = sorted(all_ids)
    orphans: list[str] = []
    for aid in sorted_ids:
        if aid == sorted_ids[0] or aid == sorted_ids[-1]:
            continue
        if aid not in referenced:
            orphans.append(aid)

    if orphans:
        issues.append(
            f"Orphan agents (not referenced by any other agent): {', '.join(orphans)}"
        )

    # Check required files exist for each agent
    for aid, d in agent_map.items():
        for fname in ("agent.md", "template.md", "checklist.md"):
            if not (d / fname).exists():
                issues.append(f"{aid}: missing {fname}")

    return issues
