"""Contract for /test-improve Phase 6 — validate via /quality-targets-converge.

Issue #536, Slice 9.

Ported from tests/skills/test_improve_phase_6_tests.bats (issue #674).
"""

from __future__ import annotations

from conftest import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_6_section() -> str:
    return section(_text(), r"^### Phase 6")


def test_body_contains_a_phase_6_section_header():
    assert grep(r"^### Phase 6", _text())


def test_phase_6_invokes_quality_targets_converge_workflow_test_improve():
    assert grep(
        r"/quality-targets-converge.*--workflow[[:space:]]+test-improve",
        _phase_6_section(),
    )


def test_phase_6_mutation_target_is_skipped_not_waived_when_phase_0_disabled_mutation():
    assert grep(
        r"mutation.*(skip|not[[:space:]]+enabled).*not[[:space:]]+waiv|not[[:space:]]+waiv.*skip",
        _phase_6_section(),
        ignore_case=True,
    )


def test_phase_6_mutation_target_is_advisory_on_go():
    assert grep(r"Go.*advisory|advisory.*Go", _phase_6_section(), ignore_case=True)


def test_phase_6_surfaces_coverage_lt_90_re_run_prompt_with_y_n_shape():
    s = _phase_6_section()
    assert grep(r"coverage.*90|<[[:space:]]*90", s, ignore_case=True)
    assert grep(r"re-run|rerun", s, ignore_case=True)
    assert grep(r"\[y/n\]|\[y\].*\[n\]", s)


def test_phase_6_coverage_lt_90_prompt_lists_backlogged_refactor_required_items():
    assert grep(r"REFACTOR_REQUIRED|backlog", _phase_6_section(), ignore_case=True)
