"""Content checks for code-review/SKILL.md's synthesis step (5c) dedup
instruction and per-finding condensation cap (issue #1774).
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "SKILL.md"

_MARKER = "#### 5c. Consolidate cross-agent findings"


def _synthesis_section() -> str:
    text = SKILL.read_text(encoding="utf-8")
    assert _MARKER in text, "synthesis step 5c heading not found"
    section = text.split(_MARKER, 1)[1].split("\n### ", 1)[0]
    return section


def test_synthesis_step_states_cross_agent_dedup_instruction() -> None:
    section = _synthesis_section()
    assert "dedup" in section.lower(), (
        "synthesis step 5c is missing an explicit cross-agent dedup instruction"
    )


def test_synthesis_step_states_numeric_condensation_cap() -> None:
    section = _synthesis_section()
    assert "3 lines per finding" in section, (
        "synthesis step 5c is missing a concrete numeric per-finding condensation cap"
    )
