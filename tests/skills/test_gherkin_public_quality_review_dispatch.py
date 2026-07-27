"""Contract for gherkin-public's adversarial dual-agent Gherkin quality
review dispatch: a new Step 4b, inserted between Step 4 (Cite the
assessment) and Step 5 (Persist phase-2 progress) — before the Step 6 human
sign-off — dispatches two independent `gherkin-quality-critic` instances
unconditionally, and Step 8's report gains two new, distinct sections for the
resulting agreed / single-source findings.

The exact per-finding line format, zero-findings sentence, and
failure-handling wording live once in
`knowledge/gherkin-quality-review-dispatch.md` (see
`tests/agents/test_gherkin_quality_critic_agent.py`) — this file asserts only
what's specific to `/gherkin-public`'s own SKILL.md: step placement, the
section names appearing, and that the step delegates to the shared doc for
format rather than re-deriving it. Symmetric with
`test_gherkin_derive_quality_review_dispatch.py`.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section_outside_code

SKILL = PLUGIN_ROOT / "skills" / "gherkin-public" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def test_step_4b_sits_between_step_4_and_step_5():
    text = _text()
    step4_idx = text.find("### 4. Cite the assessment")
    step4b_idx = text.find("### 4b. Adversarial Gherkin Quality Review")
    step5_idx = text.find("### 5. Persist phase-2 progress")
    assert step4_idx != -1
    assert step4b_idx != -1
    assert step5_idx != -1
    assert step4_idx < step4b_idx < step5_idx


def test_step_4b_names_the_agent_and_cites_shared_dispatch_doc():
    text = _text()
    scope = section_outside_code(
        text,
        r"^### 4b\. Adversarial Gherkin Quality Review",
        boundary_pattern=r"^### 5\. Persist phase-2 progress",
    )
    assert scope, "Step 4b section not found"
    assert "gherkin-quality-critic" in scope
    assert "gherkin-quality-review-dispatch.md" in scope


def test_step_4b_runs_before_the_human_sign_off():
    text = _text()
    scope = section_outside_code(
        text,
        r"^### 4b\. Adversarial Gherkin Quality Review",
        boundary_pattern=r"^### 5\. Persist phase-2 progress",
    )
    assert grep(r"before.*Step 6", scope, ignore_case=True)
    assert grep(r"before\s+the\s+Step\s+6\s+human\s+sign-off", scope, ignore_case=True)


def test_step_4b_states_no_operator_opt_in():
    text = _text()
    scope = section_outside_code(
        text,
        r"^### 4b\. Adversarial Gherkin Quality Review",
        boundary_pattern=r"^### 5\. Persist phase-2 progress",
    )
    assert grep(r"no operator opt-in", scope, ignore_case=True)
    assert grep(r"unconditionally", scope, ignore_case=True)


def test_step_8_has_two_distinct_new_report_sections():
    text = _text()
    assert grep(r'"Agreed\s+Gherkin\s+quality\s+findings"', text)
    assert grep(
        r'"Single-source\s+\(unconfirmed\)\s+Gherkin\s+quality\s+findings"', text
    )


def test_report_sections_delegate_format_to_shared_dispatch_doc():
    text = _text()
    assert grep(
        r"gherkin-quality-review-dispatch\.md.*Report section format",
        text,
        ignore_case=True,
    )


def test_report_sections_distinct_from_hand_authoring_callout():
    text = _text()
    assert grep(
        r"distinct from the\s*\n?\s*hand-authoring-flagged-components callout",
        text,
        ignore_case=True,
    )
