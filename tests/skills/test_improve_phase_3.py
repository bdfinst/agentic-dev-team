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


def test_phase_3_none_mode_documents_the_reordered_executed_sequence():
    """#1422: with Phase 3 skipped (binding mode `none`), Phase 1 follows
    Phase 2 directly under the reordered execution sequence — not Phase 4,
    which was the correct skip-target under the old sequential order."""
    s = _phase_3_section()
    assert grep(r"Phase 1 follows Phase 2", s)
    assert grep(r"0 → 2 → 1 → 4", s) or grep(r"0 -> 2 -> 1 -> 4", s)


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


def test_phase_3_names_the_human_gate_before_phase_1():
    """#1422: Phase 1 (Analyze) now immediately follows Phase 3 in the
    reordered execution sequence (0 -> 2 -> 3 -> 1 -> 4 -> ...), so Phase 3's
    human gate blocks Phase 1, not Phase 4."""
    s = _phase_3_section()
    assert grep(r"\*\*Phase 1 does not run\*\*", s)
    assert not grep(r"\*\*Phase 4 does not run\*\*", s)


def test_phase_3_human_gate_names_failure_path_gate_findings_as_part_of_approval():
    s = _phase_3_section()
    assert "gherkin_failure_path_gate.py" in s
    assert grep(r"reviewed-before-proceeding|not an inert report line", s, ignore_case=True)


def test_phase_3_documents_preserving_existing_feature_content_on_merge():
    s = _phase_3_section()
    assert grep(r"merg|preserv", s, ignore_case=True)
    assert grep(r"existing enrichment|prior content|prior enrichment", s, ignore_case=True)


def test_phase_3_has_no_overwrite_implying_language():
    assert not grep(r"overwrit", _phase_3_section(), ignore_case=True)


def test_phase_3_and_phase_5_name_the_same_remediation_for_pending_stubs():
    s = _phase_3_section()
    assert "/build" in s
    assert grep(r"same.*(pending-stub state|underlying state)|two.*checkpoints", s, ignore_case=True)
    assert grep(r"suppressed", s, ignore_case=True)
