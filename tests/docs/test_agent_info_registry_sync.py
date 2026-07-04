"""docs/agent_info.md's Review Agents table must list every review agent that
knowledge/agent-registry.md registers. The two tables drifted (agent_info.md
omitted mutation-kill and session-analysis, which exist in agents/ and are
registered in agent-registry.md) — this sensor fails loudly on future drift.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "plugins" / "dev-team"
AGENT_INFO = PLUGIN_DIR / "docs" / "agent_info.md"
AGENT_REGISTRY = PLUGIN_DIR / "knowledge" / "agent-registry.md"

_ROW_RE = re.compile(r"^\|\s*`?([a-z0-9][a-z0-9-]*)`?\s*\|")


def _section(text: str, heading: str) -> str:
    """Return the text of the section starting at `## {heading}` up to the
    next `## ` heading (or end of file)."""
    start = text.index(f"## {heading}")
    rest = text[start + len(f"## {heading}") :]
    nxt = rest.find("\n## ")
    return rest if nxt == -1 else rest[:nxt]


def _agent_names(section_text: str) -> set[str]:
    names = set()
    for line in section_text.splitlines():
        m = _ROW_RE.match(line.strip())
        if m and m.group(1) not in ("agent", "---"):
            names.add(m.group(1))
    return names


def test_agent_info_review_agents_superset_of_registry() -> None:
    registry_text = AGENT_REGISTRY.read_text(encoding="utf-8")
    info_text = AGENT_INFO.read_text(encoding="utf-8")

    registry_agents = _agent_names(_section(registry_text, "Review Agents"))
    info_agents = _agent_names(_section(info_text, "Review Agents"))

    assert registry_agents, "expected to find review-agent rows in agent-registry.md"
    missing = registry_agents - info_agents
    assert not missing, (
        f"docs/agent_info.md's Review Agents table is missing rows for: "
        f"{sorted(missing)} (present in knowledge/agent-registry.md)"
    )


def test_mutation_kill_and_session_analysis_rows_present() -> None:
    info_text = AGENT_INFO.read_text(encoding="utf-8")
    info_agents = _agent_names(_section(info_text, "Review Agents"))
    assert "mutation-kill" in info_agents
    assert "session-analysis" in info_agents
