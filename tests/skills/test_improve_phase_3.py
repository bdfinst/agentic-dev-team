"""Contract for /test-improve Phase 3 — triage via /issues-from-assessment.

Issue #536, Slice 5.

Ported from tests/skills/test_improve_phase_3_tests.bats (issue #674).
"""

from __future__ import annotations

from conftest import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_3_section() -> str:
    return section(_text(), r"^### Phase 3")


def test_body_contains_a_phase_3_section_header():
    assert grep(r"^### Phase 3", _text())


def test_phase_3_invokes_issues_from_assessment_workflow_test_improve():
    assert grep(
        r"/issues-from-assessment.*--workflow[[:space:]]+test-improve",
        _phase_3_section(),
    )


def test_phase_3_names_the_no_refactor_gap_class():
    assert grep(r"NO_REFACTOR", _phase_3_section())


def test_phase_3_names_the_refactor_required_gap_class():
    assert grep(r"REFACTOR_REQUIRED", _phase_3_section())


def test_phase_3_names_the_low_value_gap_class():
    assert grep(r"LOW_VALUE", _phase_3_section())


def test_phase_3_documents_low_value_as_advisory_only():
    assert grep(
        r"LOW_VALUE.*(advisory|no[[:space:]]+PR|no[[:space:]]+deletion|not[[:space:]]+delet)",
        _phase_3_section(),
        ignore_case=True,
    )


def test_phase_3_documents_refactor_required_deferral_to_phase_5():
    assert grep(
        r"REFACTOR_REQUIRED.*(defer|Phase[[:space:]]+5|not[[:space:]]+written)|"
        r"Phase[[:space:]]+5.*REFACTOR_REQUIRED",
        _phase_3_section(),
        ignore_case=True,
    )


def test_phase_3_writes_no_refactor_items_as_phase_4_stories():
    assert grep(
        r"NO_REFACTOR.*(Phase[- ]4|Stor[iy])|Stor[iy].*Phase[- ]4",
        _phase_3_section(),
        ignore_case=True,
    )


def test_phase_3_names_the_human_gate_blocking_phase_4():
    assert grep(
        r"human[[:space:]]+gate|Phase[[:space:]]+4.*(does[[:space:]]+not|not)[[:space:]]+run|approv",
        _phase_3_section(),
        ignore_case=True,
    )
