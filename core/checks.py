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
    meta_map: dict[str, dict[str, object]] = {}
    for d in agents:
        try:
            fm, _ = load_agent_doc(d)
            aid = str(fm.get("id", ""))
            if not aid:
                issues.append(f"{d.name}: missing 'id' in frontmatter")
                continue
            if aid in agent_map:
                issues.append(f"{d.name}: duplicate agent id '{aid}'")
                continue
            agent_map[aid] = d
            meta_map[aid] = fm
        except FileNotFoundError:
            issues.append(f"{d.name}: agent.md not found")
            continue

    # Check upstream/downstream references point to existing agents
    for aid, fm in meta_map.items():
        upstream: list[str] = fm.get("upstream", [])
        downstream: list[str] = fm.get("downstream", [])

        for u in upstream:
            if u not in agent_map:
                issues.append(f"{aid}: upstream agent '{u}' not found")
            elif aid not in meta_map[u].get("downstream", []):
                issues.append(f"{aid}: upstream agent '{u}' does not list '{aid}' as downstream")

        for dw in downstream:
            if dw not in agent_map:
                issues.append(f"{aid}: downstream agent '{dw}' not found")
            elif aid not in meta_map[dw].get("upstream", []):
                issues.append(f"{aid}: downstream agent '{dw}' does not list '{aid}' as upstream")

    # Check sequential chain shape. Agents are ordered by id: the first stage
    # has no upstream, the last stage has no downstream, and intermediate
    # stages must be connected on both sides.
    sorted_ids = sorted(agent_map)
    if sorted_ids:
        first_id = sorted_ids[0]
        last_id = sorted_ids[-1]
        for aid in sorted_ids:
            upstream = meta_map[aid].get("upstream", [])
            downstream = meta_map[aid].get("downstream", [])
            if aid == first_id and upstream:
                issues.append(f"{aid}: first agent should not have upstream agents")
            if aid != first_id and not upstream:
                issues.append(f"{aid}: missing upstream agent")
            if aid == last_id and downstream:
                issues.append(f"{aid}: last agent should not have downstream agents")
            if aid != last_id and not downstream:
                issues.append(f"{aid}: missing downstream agent")

    # Check required files exist for each agent
    for aid, d in agent_map.items():
        for fname in ("agent.md", "template.md", "checklist.md"):
            if not (d / fname).exists():
                issues.append(f"{aid}: missing {fname}")

    return issues
