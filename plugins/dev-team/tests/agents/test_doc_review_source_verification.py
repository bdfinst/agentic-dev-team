"""Structural cross-reference check for doc-review.md -> source-verification
(#2189, plan step 3.3).

doc-review's scope already covers doc accuracy, so it is the internal
consumer wired to /source-verification's claim-extraction/verification
procedure for claims about external APIs/tools — otherwise the skill ships
orphaned. This is structural-only coverage (the reference exists), matching
this repo's existing convention for cross-skill wiring checks (see
test_security_review_scope_language.py for the same grep-based pattern
against a different agent file).
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "doc-review.md"


def _text() -> str:
    return AGENT.read_text(encoding="utf-8")


def test_references_source_verification_skill() -> None:
    text = _text()
    assert "source-verification" in text, (
        "doc-review.md should reference the source-verification skill so it "
        "doesn't ship as an orphaned skill (#2189)"
    )


def test_source_verification_reference_is_in_detect_section() -> None:
    """The reference should live under ## Detect, alongside doc-review's
    other checks, not just be a stray mention (e.g. in a comment)."""
    text = _text()
    assert "## Detect" in text
    detect_section = text.split("## Detect", 1)[1].split("\n## Self-Challenge", 1)[0]
    assert "source-verification" in detect_section, (
        "the source-verification reference should be part of a Detect "
        "subsection describing when doc-review invokes it"
    )
