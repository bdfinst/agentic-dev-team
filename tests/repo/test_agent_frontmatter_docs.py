"""Non-standard agent body declarations must be documented (issue #732).

`Cites:` (used by ~32 agents) and `Enforcement: script` (used by 5 agents)
are intentional internal tooling metadata read by `scripts/citation_lint.py`
and the "Implemented by:" agent convention respectively — not schema errors.
Both are body-level declarations, not frontmatter (issue #1333 — neither is
part of the official Claude Code sub-agent contract). This guard checks that
a real doc explains both, so a future contributor auditing agent frontmatter
doesn't mistake them for drift.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "plugins" / "dev-team" / "docs" / "agent_info.md"


def test_agent_info_doc_explains_cites_declaration() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "`Cites:" in text, (
        f"{DOC} should document the `Cites:` body declaration used by "
        "review agents to declare their canonical knowledge sources."
    )
    assert "citation_lint.py" in text, (
        f"{DOC} should reference scripts/citation_lint.py, the tool that "
        "consumes the `Cites:` declaration."
    )


def test_agent_info_doc_explains_enforcement_script_declaration() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "`Enforcement: script`" in text, (
        f"{DOC} should document the `Enforcement: script` body declaration "
        "used by deterministic-script-backed agents."
    )
