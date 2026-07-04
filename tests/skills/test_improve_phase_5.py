"""Contract for /test-improve Phase 5 — refactor-for-testability (conditional
on [y] from Phase 4b). Issue #536, Slice 8.

Ported from tests/skills/test_improve_phase_5_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_5_section() -> str:
    return section(_text(), r"^### Phase 5")


def test_body_contains_a_phase_5_section_header():
    assert grep(r"^### Phase 5", _text())


def test_phase_5_is_conditional_on_y_from_phase_4b():
    assert grep(
        r"\[y\].*Phase[[:space:]]+4b|Phase[[:space:]]+4b.*\[y\]|only[[:space:]]+(when|if)|conditional",
        _phase_5_section(),
        ignore_case=True,
    )


def test_phase_5_documents_seam_only_production_code_constraint():
    assert grep(
        r"seam[[:space:]]*(only|-only|introduction)",
        _phase_5_section(),
        ignore_case=True,
    )


def test_phase_5_forbids_modification_or_removal_of_existing_tests():
    assert grep(
        r"existing[[:space:]]+tests?[^.]*(may[[:space:]]+not|not).*(modif|delet|remov|edit)|"
        r"(not[[:space:]]+modif|not[[:space:]]+delet|not[[:space:]]+remov).*existing[[:space:]]+tests?",
        _phase_5_section(),
        ignore_case=True,
    )


def test_phase_5_documents_phase_4_precondition_check_on_paired_stories():
    assert grep(
        r"precondition|Phase-4[[:space:]]+.*(closed|green)|verif.*Phase[[:space:]]+4",
        _phase_5_section(),
        ignore_case=True,
    )


def test_phase_5_references_the_same_review_loop_schema_as_phase_4():
    assert grep(
        r"same[[:space:]]+.*review[[:space:]]+loop|Phase[[:space:]]+4[[:space:]]+.*review[[:space:]]+loop|"
        r"review[[:space:]]+loop.*Phase[[:space:]]+4",
        _phase_5_section(),
        ignore_case=True,
    )


def test_phase_5_writes_phase_5_review_json_with_the_review_loop_schema():
    assert grep(r"memory/test-improve/<slug>/phase-5-review\.json", _phase_5_section())
