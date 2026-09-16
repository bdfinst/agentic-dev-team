"""Doc-shape contract for the /specs completeness sweep (epic #2159, issue #2161).

`plan-review-acceptance` checks whether each criterion a spec *contains* is
complete. A spec that never mentions deletion produces no criterion for it to
find incomplete — the omission is the absence of a criterion, and absence is
structurally invisible to every per-criterion check.

The sweep enumerates the entities a spec names and checks each against a fixed
checklist, so what the spec failed to mention becomes a finding rather than a
silence. These guards pin its placement, its reporting obligations, its
routing through the existing protocol, and — most importantly — the boundary
that keeps it from duplicating `plan-review-acceptance`.
"""

from __future__ import annotations

import pytest
from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep

SKILL = PLUGIN_ROOT / "skills" / "specs" / "SKILL.md"
CHECKLIST = (
    PLUGIN_ROOT / "skills" / "specs" / "references" / "completeness-checklist.md"
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    return collapsed(SKILL.read_text())


@pytest.fixture(scope="module")
def checklist_text() -> str:
    return collapsed(CHECKLIST.read_text())


# --- placement -------------------------------------------------------------


def test_the_checklist_exists():
    assert CHECKLIST.is_file()


def test_sweep_runs_after_critique_and_before_the_gate(skill_text):
    assert grep(
        r"after the critique loop and \*\*before\*\* the Consistency Gate",
        skill_text,
        ignore_case=True,
    )


def test_sweep_appears_before_the_gate_in_the_document():
    """Placement is structural, not just asserted in prose."""
    raw = SKILL.read_text()
    assert raw.index("## Completeness sweep") < raw.index(
        "## Cross-Artifact Consistency Gate"
    )


def test_checklist_is_loaded_on_demand(skill_text):
    assert "references/completeness-checklist.md" in SKILL.read_text()


def test_skill_does_not_inline_the_checklist_body(skill_text):
    """Progressive disclosure: the step and its routing live here, the
    checklist's own cells live in the reference (epic #2159 constraint)."""
    raw = SKILL.read_text()
    assert "How does one come into existence?" not in raw


# --- the checklist's fixed content -----------------------------------------


@pytest.mark.parametrize("operation", ["Create", "Read", "Update", "Delete"])
def test_checklist_covers_every_crud_operation(checklist_text, operation):
    assert grep(rf"\*\*{operation}\*\*", checklist_text)


@pytest.mark.parametrize(
    "concern", ["Authentication", "Authorization", "Audit", "Error handling"]
)
def test_checklist_covers_every_cross_cutting_concern(checklist_text, concern):
    assert grep(rf"\*\*{concern}", checklist_text, ignore_case=True)


def test_skill_names_all_four_concerns_so_the_step_is_self_contained(skill_text):
    for concern in ("authentication", "authorization", "audit", "error handling"):
        assert grep(concern, skill_text, ignore_case=True), (
            f"{concern!r} unnamed in SKILL.md"
        )


def test_checklist_declares_itself_non_extensible(checklist_text):
    assert grep(r"not extensible per project", checklist_text, ignore_case=True)
    assert grep(r"speculative design", checklist_text, ignore_case=True)


def test_checklist_covers_domain_implied_surfaces(checklist_text):
    assert grep(r"domain-implied surfaces", checklist_text, ignore_case=True)


# --- reporting obligations -------------------------------------------------


def test_enumerated_entities_must_be_reported(skill_text):
    assert grep(r"report the entities you enumerated", skill_text, ignore_case=True)


def test_enumeration_is_acknowledged_as_a_model_step(checklist_text):
    """CLAUDE.md prefers deterministic tools; this one genuinely cannot be, so
    the mitigation is showing the list rather than pretending otherwise.

    The requirement lives in SKILL.md (test_enumerated_entities_must_be_reported);
    the rationale lives here, so SKILL.md does not restate the reference."""
    assert grep(r"model step, not a parser", checklist_text, ignore_case=True)


def test_findings_are_grouped_by_entity(skill_text):
    """The requirement is in SKILL.md so an agent following it knows to do
    this; only the reasoning lives in the reference."""
    assert grep(r"group findings by entity", skill_text, ignore_case=True)


def test_one_answer_cells_are_separated_from_individual_judgment(checklist_text):
    assert grep(r"dispositionable in one answer", checklist_text, ignore_case=True)


def test_grouping_states_why_a_flat_dump_is_harmful(checklist_text):
    assert grep(r"rubber-stamping", checklist_text, ignore_case=True)


# --- routing ---------------------------------------------------------------


def test_each_unaddressed_cell_routes_into_the_ambiguity_log(skill_text):
    assert grep(r"route each unaddressed cell", skill_text, ignore_case=True)
    raw = SKILL.read_text()
    assert "`inferable`" in raw and "`requires-stakeholder-input`" in raw


def test_an_inapplicable_cell_is_recorded_not_dropped(skill_text):
    assert grep(r"never dropped", skill_text, ignore_case=True)


def test_read_only_by_design_is_the_worked_example(skill_text):
    assert grep(r"read-only by design", skill_text, ignore_case=True)


def test_the_sweep_is_not_a_gate(skill_text):
    assert grep(r"the sweep is not a gate", skill_text, ignore_case=True)


def test_no_new_gate_severity_scheme_or_confidence_score(skill_text):
    assert grep(
        r"no new gate, severity scheme, or confidence score",
        skill_text,
        ignore_case=True,
    )


# --- division of labor with plan-review-acceptance -------------------------


def test_skill_states_the_boundary_with_plan_review_acceptance(skill_text):
    assert grep(r"plan-review-acceptance", skill_text)
    assert grep(
        r"never grades a criterion that already exists", skill_text, ignore_case=True
    )


def test_skill_names_the_two_distinct_questions(skill_text):
    assert grep(r"is there a criterion here at all", skill_text, ignore_case=True)
    assert grep(r"is this criterion complete", skill_text, ignore_case=True)


def test_checklist_repeats_the_boundary_so_it_survives_edits(checklist_text):
    assert grep(
        r"never grades a criterion that exists", checklist_text, ignore_case=True
    )
    assert grep(r"plan-review-acceptance", checklist_text)
