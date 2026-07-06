"""Content-guard for triage/SKILL.md's unconfirmed-outcome schema (issue #918,
sub-issues #924-#927).

`/triage` used to have a binary outcome (confirmed root cause vs. "not
determined"), which incentivized rounding an unverified, adjacent finding up
to full "root cause" status rather than admitting partial failure. These
guards assert the third `unconfirmed` outcome, the pre-write verification
checkpoint that routes into it, and the two investigation-time triggers
(cross-service/intermittent evidence request, boundary dead-end naming) all
stay present and correctly worded.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL_MD = PLUGIN_ROOT / "skills" / "triage" / "SKILL.md"


def _text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _collapsed(text: str) -> str:
    """Join hard-wrapped prose lines so a phrase split across a markdown
    line-wrap still matches a plain substring check."""
    return re.sub(r"\s+", " ", text)


def _constraints_section(text: str) -> str:
    return section(text, r"^## Worker constraints", boundary_pattern=r"^## ")


def _step(text: str, heading_pattern: str) -> str:
    return section(text, heading_pattern, boundary_pattern=r"^### ")


# ---------------------------------------------------------------------------
# #924 — confidence field, unconfirmed banner, fix-plan framing, worker
# constraint, three-outcome documentation
# ---------------------------------------------------------------------------


def test_confidence_field_present_in_record_template() -> None:
    text = _text()
    assert grep(r"^confidence: confirmed$", text)
    assert grep(r"omitted/absent defaults to `confirmed`", text)


def test_unconfirmed_banner_present() -> None:
    text = _text()
    assert (
        "> **UNCONFIRMED** — contributing factor identified; "
        "not verified against the reported symptom." in text
    )


def test_unconfirmed_fix_plan_framing_present() -> None:
    collapsed = _collapsed(_text())
    assert (
        'frame the plan as addressing "the identified contributing factor," '
        "not the confirmed root cause" in collapsed
    )


def test_worker_constraint_two_tightened() -> None:
    constraints = _collapsed(_constraints_section(_text()))
    assert "do not record on symptoms alone" in constraints
    assert (
        "do not record an unverified, unrelated finding as if it were the "
        "root cause" in constraints
    )
    assert "use the `unconfirmed` outcome instead" in constraints


def test_three_outcomes_documented_as_distinct() -> None:
    text = _text()
    assert "mutually distinct" in text
    assert "**`confirmed`**" in text
    assert "**`unconfirmed`**" in text
    assert "**not determined**" in text


# ---------------------------------------------------------------------------
# #925 — pre-write verification checkpoint
# ---------------------------------------------------------------------------


def test_verification_checkpoint_step_present_between_step_3_and_5() -> None:
    text = _text()
    assert grep(r"^### 3\. Design TDD Fix Plan$", text)
    assert grep(r"^### 4\. Verification Checkpoint$", text)
    assert grep(r"^### 5\. Write the Triage Record$", text)


def test_checkpoint_routes_failure_to_unconfirmed() -> None:
    checkpoint = _step(_text(), r"^### 4\. Verification Checkpoint$")
    assert "route to the" in checkpoint
    assert "`unconfirmed` outcome" in checkpoint


def test_checkpoint_is_a_hard_gate_not_optional() -> None:
    checkpoint = _step(_text(), r"^### 4\. Verification Checkpoint$")
    assert "Hard gate" in checkpoint
    assert "cannot be skipped implicitly" in checkpoint
    assert "no silent pass-through" in checkpoint.lower()


# ---------------------------------------------------------------------------
# #926 — Step 1 evidence question for cross-service/intermittent bugs
# ---------------------------------------------------------------------------


def test_step_1_names_the_trigger_condition() -> None:
    step1 = _step(_text(), r"^### 1\. Capture the Problem$")
    assert "cross-service or" in step1
    assert "intermittent" in step1
    assert '"sometimes"' in step1
    assert '"inconsistently"' in step1


def test_step_1_asks_single_targeted_evidence_question() -> None:
    step1 = _step(_text(), r"^### 1\. Capture the Problem$")
    for category in (
        "logs",
        "sample request/response",
        "trace/audit IDs",
        "config/pipeline export",
    ):
        assert category in step1


def test_step_1_existing_ask_nothing_rule_preserved() -> None:
    step1 = _step(_text(), r"^### 1\. Capture the Problem$")
    assert "ask nothing — start investigating immediately" in step1
    assert "narrow exception" in step1


def test_step_1_no_description_fallback_unchanged() -> None:
    step1 = _step(_text(), r"^### 1\. Capture the Problem$")
    assert "What's the problem you're seeing?" in step1


# ---------------------------------------------------------------------------
# #927 — boundary dead-end named as "producer not located in scope"
# ---------------------------------------------------------------------------


def test_step_2_names_boundary_dead_end_condition() -> None:
    step2 = _step(_text(), r"^### 2\. Investigate$")
    assert "zero hits" in step2
    assert "checked-out repos" in step2


def test_step_2_dead_end_outcome_named_not_silently_continued() -> None:
    step2 = _step(_text(), r"^### 2\. Investigate$")
    assert "producer not located in scope" in step2
    assert "do not keep searching" in step2


def test_step_2_dead_end_routes_to_verification_checkpoint() -> None:
    step2 = _step(_text(), r"^### 2\. Investigate$")
    assert "Verification Checkpoint (Step 4)" in step2
    assert "`unconfirmed` outcome" in step2
