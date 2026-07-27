"""Contract for gherkin-derive's adversarial dual-agent Gherkin quality
review dispatch (issue #1452): a new Step 5b, inserted between Step 5
(Output) and Step 6 (Report), dispatches two independent
`gherkin-quality-review` instances whenever `.feature` files were written or
merged, and Step 6 gains two new, distinct report sections for the resulting
agreed / single-source findings.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section_outside_code

SKILL = PLUGIN_ROOT / "skills" / "gherkin-derive" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def test_step_5b_sits_between_step_5_and_step_6():
    text = _text()
    step5_idx = text.find("## Step 5 — Output")
    step5b_idx = text.find("## Step 5b — Adversarial Gherkin Quality Review")
    step6_idx = text.find("## Step 6 — Report")
    assert step5_idx != -1
    assert step5b_idx != -1
    assert step6_idx != -1
    assert step5_idx < step5b_idx < step6_idx


def test_step_5b_names_the_agent_and_cites_shared_dispatch_doc():
    text = _text()
    scope = section_outside_code(
        text,
        r"^## Step 5b — Adversarial Gherkin Quality Review",
        boundary_pattern=r"^## Step 6 — Report",
    )
    assert scope, "Step 5b section not found"
    assert "gherkin-quality-review" in scope
    assert "gherkin-quality-review-dispatch.md" in scope


def test_step_5b_states_the_skip_conditions():
    text = _text()
    scope = section_outside_code(
        text,
        r"^## Step 5b — Adversarial Gherkin Quality Review",
        boundary_pattern=r"^## Step 6 — Report",
    )
    assert grep(r"none.*mode", scope, ignore_case=True)
    assert grep(r"zero|no operator opt-in", scope, ignore_case=True)


def test_step_5b_states_no_operator_opt_in():
    text = _text()
    scope = section_outside_code(
        text,
        r"^## Step 5b — Adversarial Gherkin Quality Review",
        boundary_pattern=r"^## Step 6 — Report",
    )
    assert grep(r"no operator opt-in", scope, ignore_case=True)


def test_step_6_has_two_distinct_new_report_sections():
    text = _text()
    assert '"Agreed Gherkin quality findings"' in text
    assert '"Single-source (unconfirmed) Gherkin quality findings"' in text


def test_report_sections_state_zero_findings_and_failure_handling():
    text = _text()
    assert grep(r"None — both instances raised no findings", text)
    assert grep(
        r"failed.*unparseable|shared dispatch doc.*failure", text, ignore_case=True
    )


def test_report_sections_never_folded_into_other_callouts():
    text = _text()
    assert grep(
        r"Neither section is folded into the characterization",
        text,
        ignore_case=True,
    )
