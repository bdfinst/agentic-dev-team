"""Issue #1461 — the doc-only short-circuit's `.review-passed` write must be
paired with an explicit, auditable boundary event (`"doc-only-review-exempt"`)
rather than a silent code-path skip, so the dispatch-ledger corroboration
gate can recognize the exemption instead of only seeing an uncorroborated
hash-matching write.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT

CODE_REVIEW = (
    PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md"
).read_text(encoding="utf-8")


def test_doc_only_short_circuit_emits_the_exemption_boundary_event():
    assert "doc-only-review-exempt" in CODE_REVIEW, (
        "the doc-only short-circuit must record a doc-only-review-exempt "
        "boundary event contemporaneously with its .review-passed write"
    )


def test_doc_only_exemption_invokes_boundary_events_cli_with_bypass_decision():
    assert "hooks/lib/boundary_events.py" in CODE_REVIEW
    assert "--decision bypass" in CODE_REVIEW
    assert "--matched-rule doc-only-review-exempt" in CODE_REVIEW
