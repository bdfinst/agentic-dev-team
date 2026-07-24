"""Contract for /test-improve Phase 7 — refactor-for-testability (conditional
on [y] from Phase 6). Issue #536, Slice 8.

Ported from tests/skills/test_improve_phase_5_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_7_section() -> str:
    return section(_text(), r"^### Phase 7")


def test_body_contains_a_phase_7_section_header():
    assert grep(r"^### Phase 7", _text())


def test_phase_7_is_conditional_on_y_from_phase_6():
    assert grep(
        r"\[y\].*Phase[[:space:]]+6|Phase[[:space:]]+6.*\[y\]|only[[:space:]]+(when|if)|conditional",
        _phase_7_section(),
        ignore_case=True,
    )


def test_phase_7_documents_seam_only_production_code_constraint():
    assert grep(
        r"seam[[:space:]]*(only|-only|introduction)",
        _phase_7_section(),
        ignore_case=True,
    )


def test_phase_7_forbids_modification_or_removal_of_existing_tests():
    assert grep(
        r"existing[[:space:]]+tests?[^.]*(may[[:space:]]+not|not).*(modif|delet|remov|edit)|"
        r"(not[[:space:]]+modif|not[[:space:]]+delet|not[[:space:]]+remov).*existing[[:space:]]+tests?",
        _phase_7_section(),
        ignore_case=True,
    )


def test_phase_7_documents_phase_5_precondition_check_on_paired_stories():
    assert grep(
        r"precondition|Phase-5[[:space:]]+.*(closed|green)|verif.*Phase[[:space:]]+5",
        _phase_7_section(),
        ignore_case=True,
    )


def test_phase_7_references_the_same_review_loop_schema_as_phase_5():
    assert grep(
        r"same[[:space:]]+.*review[[:space:]]+loop|Phase[[:space:]]+5[[:space:]]+.*review[[:space:]]+loop|"
        r"review[[:space:]]+loop.*Phase[[:space:]]+5",
        _phase_7_section(),
        ignore_case=True,
    )


def test_phase_7_writes_phase_7_review_json_with_the_review_loop_schema():
    assert grep(r"memory/test-improve/<slug>/phase-7-review\.json", _phase_7_section())
