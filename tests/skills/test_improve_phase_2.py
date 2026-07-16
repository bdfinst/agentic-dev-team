"""Contract for /test-improve Phase 2 — baseline coverage + mutation before
any test change. Issue #536, Slice 3.

Ported from tests/skills/test_improve_phase_2_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

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


def test_phase_2_invokes_mutation_testing_baseline_only_in_baseline_kill_loop_mode():
    """#1126: the Phase-2 mutation baseline runs only in `baseline+kill-loop`
    mode (not `off`, not `kill-loop`)."""
    s = _phase_2_section()
    assert grep(
        r"/mutation-testing.*--baseline.*--workflow[[:space:]]+test-improve|"
        r"--workflow[[:space:]]+test-improve.*--baseline",
        s,
    )
    assert grep(r"baseline\+kill-loop", s)


def test_phase_2_names_the_ordering_constraint_baseline_before_any_test_file_modified():
    assert grep(
        r"before[^.]*(any[[:space:]]+(file[[:space:]]+under[[:space:]]+)?tests?/|"
        r"any[[:space:]]+test[[:space:]]+file|any[[:space:]]+test[[:space:]]+is[[:space:]]+modified|"
        r"test.*(modif|edit|chang))",
        _phase_2_section(),
        ignore_case=True,
    )


def test_phase_2_documents_the_no_baseline_skip_path_for_off_and_kill_loop():
    """#1126: both `off` and `kill-loop` skip the Phase-2 mutation baseline —
    `kill-loop` runs the kill loop in Phase 4 but takes no baseline first."""
    s = _phase_2_section()
    # The skip is documented and names both no-baseline modes.
    assert grep(r"not[[:space:]]+invoked|skip", s, ignore_case=True)
    assert grep(r"`off`", s) and grep(r"`kill-loop`", s)
    assert grep(r"no[[:space:]]+baseline|takes[[:space:]]+no[[:space:]]+baseline", s, ignore_case=True)


def test_phase_2_records_baseline_artifacts_under_memory_test_improve_slug():
    s = _phase_2_section()
    assert grep(r"memory/test-improve/<slug>/baseline-coverage\.json", s)
    assert grep(r"memory/test-improve/<slug>/baseline-mutation\.json", s)


def test_phase_2_baseline_write_path_is_conditional_on_report_opt_in():
    """#1126: on knob-7 opt-in, the baseline is written to a git-tracked
    reports/test-improve/ path (picked up by the run's PR); on decline it
    stays on the transient memory/ path. No git command is issued."""
    s = _phase_2_section()
    assert grep(r"reports/test-improve/<slug>/", s)
    assert grep(r"git-tracked", s)
    assert grep(r"transient|memory/test-improve/<slug>/", s)
    assert grep(r"no.*git command|issues.*no.*git", s, ignore_case=True)


def test_phase_2_documents_the_reports_gitignore_caveat():
    """#1126: because reports/ is commonly gitignored, the target repo must
    un-ignore reports/test-improve/ or the opt-in degrades to transient."""
    s = _phase_2_section()
    assert grep(r"gitignore|un-ignore", s, ignore_case=True)
    assert grep(r"degrades? to transient|degrade", s, ignore_case=True)


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
