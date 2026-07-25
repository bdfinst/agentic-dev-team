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
    return section(_text(), r"^### Phase 2", exclude_pattern=r"Phase 3")


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
    `kill-loop` runs the kill loop in Phase 5 but takes no baseline first."""
    s = _phase_2_section()
    # The skip is documented and names both no-baseline modes.
    assert grep(r"not[[:space:]]+invoked|skip", s, ignore_case=True)
    assert grep(r"`off`", s) and grep(r"`kill-loop`", s)
    assert grep(r"no[[:space:]]+baseline|takes[[:space:]]+no[[:space:]]+baseline", s, ignore_case=True)


def test_phase_2_records_baseline_artifacts_under_memory_test_improve_slug():
    s = _phase_2_section()
    assert grep(r"memory/test-improve/<slug>/baseline-coverage\.json", s)
    assert grep(r"memory/test-improve/<slug>/baseline-mutation\.json", s)


def test_phase_2_baseline_write_is_unconditional_not_report_opt_in_gated():
    """#1412: knob-7 is gone — Phase 2's own baseline write is a single,
    unconditional path (/coverage-baseline's canonical memory/ write, itself
    untouched); no report-opt-in branching remains at Phase 2."""
    s = _phase_2_section()
    assert grep(r"unconditional", s, ignore_case=True)
    assert grep(r"memory/test-improve/<slug>/baseline-coverage\.json", s)
    assert not grep(r"report opt-in|knob-7", s, ignore_case=True)


def test_phase_2_defers_the_tracked_data_copy_to_phase_9():
    """#1412: the git-tracked data/ copy is produced later, unconditionally,
    by Phase 9 — Phase 2's own text says so and stops short of describing
    that copy step itself (owned by Phase 9)."""
    s = _phase_2_section()
    assert grep(r"Phase 9", s)
    assert grep(r"data/", s)


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
