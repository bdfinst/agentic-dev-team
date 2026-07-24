"""Contract for /test-improve Phase 4 — triage via /issues-from-assessment.

Issue #536, Slice 5.

Ported from tests/skills/test_improve_phase_3_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_4_section() -> str:
    return section(_text(), r"^### Phase 4")


def test_body_contains_a_phase_4_section_header():
    assert grep(r"^### Phase 4", _text())


def test_phase_4_invokes_issues_from_assessment_workflow_test_improve():
    assert grep(
        r"/issues-from-assessment.*--workflow[[:space:]]+test-improve",
        _phase_4_section(),
    )


def test_phase_4_names_the_no_refactor_gap_class():
    assert grep(r"NO_REFACTOR", _phase_4_section())


def test_phase_4_names_the_refactor_required_gap_class():
    assert grep(r"REFACTOR_REQUIRED", _phase_4_section())


def test_phase_4_names_the_low_value_gap_class():
    assert grep(r"LOW_VALUE", _phase_4_section())


def test_phase_4_documents_low_value_as_advisory_only():
    assert grep(
        r"LOW_VALUE.*(advisory|no[[:space:]]+PR|no[[:space:]]+deletion|not[[:space:]]+delet)",
        _phase_4_section(),
        ignore_case=True,
    )


def test_phase_4_documents_refactor_required_deferral_to_phase_7():
    assert grep(
        r"REFACTOR_REQUIRED.*(defer|Phase[[:space:]]+7|not[[:space:]]+written)|"
        r"Phase[[:space:]]+7.*REFACTOR_REQUIRED",
        _phase_4_section(),
        ignore_case=True,
    )


def test_phase_4_writes_no_refactor_items_as_phase_5_stories():
    assert grep(
        r"NO_REFACTOR.*(Phase[- ]5|Stor[iy])|Stor[iy].*Phase[- ]5",
        _phase_4_section(),
        ignore_case=True,
    )


def test_phase_4_names_the_human_gate_blocking_phase_5():
    assert grep(
        r"human[[:space:]]+gate|Phase[[:space:]]+5.*(does[[:space:]]+not|not)[[:space:]]+run|approv",
        _phase_4_section(),
        ignore_case=True,
    )
