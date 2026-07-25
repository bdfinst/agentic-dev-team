"""Contract for /test-improve Phase 3 — derive Gherkin only when binding
mode is not "none". Issue #536, Slice 4.

Ported from tests/skills/test_improve_phase_2b_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_3_section() -> str:
    return section(_text(), r"^### Phase 3")


def test_body_contains_a_phase_3_section_header():
    assert grep(r"^### Phase 3", _text())


def test_phase_3_names_gherkin_derive_workflow_test_improve():
    assert grep(
        r"/gherkin-derive.*--workflow[[:space:]]+test-improve", _phase_3_section()
    )


def test_phase_3_documents_binding_mode_none_skip_path():
    assert grep(
        r"none.*(skip|not[[:space:]]+invok|omit)|when[[:space:]]+.*none",
        _phase_3_section(),
        ignore_case=True,
    )


def test_phase_3_documents_xunit_with_annotations_mode_no_runner_added():
    s = _phase_3_section()
    assert grep(r"xunit-with-annotations", s)
    assert grep(
        r"no[[:space:]]+runner|without[[:space:]]+.*runner|no[[:space:]]+.*dependency",
        s,
        ignore_case=True,
    )


def test_phase_3_documents_bdd_runner_mode_native_parser_wired():
    s = _phase_3_section()
    assert grep(r"bdd-runner", s)
    assert grep(r"parser|cucumber|specflow|reqnroll", s, ignore_case=True)


def test_phase_3_writes_feature_files_under_features_test_improve():
    assert grep(r"features/test-improve/", _phase_3_section())


def test_phase_3_names_memory_test_improve_slug_gherkin_md_persistence():
    assert grep(r"memory/test-improve/<slug>/gherkin\.md", _phase_3_section())


def test_phase_3_names_the_human_gate_before_phase_4():
    assert grep(
        r"human[[:space:]]+gate|Phase[[:space:]]+4.*(does[[:space:]]+not|not)[[:space:]]+run|approv",
        _phase_3_section(),
        ignore_case=True,
    )


def test_phase_3_human_gate_names_failure_path_gate_findings_as_part_of_approval():
    s = _phase_3_section()
    assert "gherkin_failure_path_gate.py" in s
    assert grep(r"reviewed-before-proceeding|not an inert report line", s, ignore_case=True)
