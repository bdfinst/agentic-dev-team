"""Non-standard agent frontmatter keys must be documented (issue #732).

`cites:` (used by 22 agents) and `enforcement: script` (used by 5 agents) are
intentional internal tooling metadata read by `scripts/citation_lint.py` and
the "Implemented by:" agent convention respectively — not schema errors. This
guard checks that a real doc explains both, so a future contributor auditing
agent frontmatter doesn't mistake them for drift.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "plugins" / "dev-team" / "docs" / "agent_info.md"


def test_agent_info_doc_explains_cites_frontmatter_key() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "`cites:`" in text, (
        f"{DOC} should document the `cites:` frontmatter key used by "
        "review agents to declare their canonical knowledge sources."
    )
    assert "citation_lint.py" in text, (
        f"{DOC} should reference scripts/citation_lint.py, the tool that "
        "consumes the `cites:` frontmatter key."
    )


def test_agent_info_doc_explains_enforcement_script_frontmatter_key() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "`enforcement: script`" in text, (
        f"{DOC} should document the `enforcement: script` frontmatter key "
        "used by deterministic-script-backed agents."
    )
