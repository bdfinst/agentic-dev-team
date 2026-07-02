"""Contract for /test-improve Phase 2 — baseline coverage + mutation before
any test change. Issue #536, Slice 3.

Ported from tests/skills/test_improve_phase_2_tests.bats (issue #674).
"""

from __future__ import annotations

from conftest import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_2_section() -> str:
    return section(_text(), r"^### Phase 2", exclude_pattern=r"Phase 2b")


def test_body_contains_a_phase_2_section_header():
    assert grep(r"^### Phase 2( —|$| \()", _text())


def test_phase_2_invokes_coverage_baseline_with_workflow_test_improve():
    assert grep(
        r"/coverage-baseline.*--workflow[[:space:]]+test-improve", _phase_2_section()
    )


def test_phase_2_invokes_mutation_testing_baseline_workflow_test_improve_when_mutation_is_on():
    assert grep(
        r"/mutation-testing.*--baseline.*--workflow[[:space:]]+test-improve|"
        r"--workflow[[:space:]]+test-improve.*--baseline",
        _phase_2_section(),
    )


def test_phase_2_names_the_ordering_constraint_baseline_before_any_test_file_modified():
    assert grep(
        r"before[^.]*(any[[:space:]]+(file[[:space:]]+under[[:space:]]+)?tests?/|"
        r"any[[:space:]]+test[[:space:]]+file|any[[:space:]]+test[[:space:]]+is[[:space:]]+modified|"
        r"test.*(modif|edit|chang))",
        _phase_2_section(),
        ignore_case=True,
    )


def test_phase_2_documents_the_mutation_off_skip_path():
    assert grep(
        r"mutation.*off.*(skip|not[[:space:]]+(invoke|run)|omit)|"
        r"when[[:space:]]+mutation[[:space:]]+is[[:space:]]+off",
        _phase_2_section(),
        ignore_case=True,
    )


def test_phase_2_records_baseline_artifacts_under_memory_test_improve_slug():
    s = _phase_2_section()
    assert grep(r"memory/test-improve/<slug>/baseline-coverage\.json", s)
    assert grep(r"memory/test-improve/<slug>/baseline-mutation\.json", s)


def test_phase_2_documents_the_go_advisory_marker_on_mutation_baseline():
    assert grep(
        r"go.*(advisory|advisory-only)|advisory[- ]only.*go",
        _phase_2_section(),
        ignore_case=True,
    )


def test_phase_2_mutation_baseline_records_the_honest_score_hard_kills_timeouts_separate():
    s = _phase_2_section()
    assert grep(r"hard[[:space:]]+kill", s, ignore_case=True)
    assert grep(r"timeout", s, ignore_case=True)
