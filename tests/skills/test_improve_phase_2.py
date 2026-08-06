"""Contract for /test-improve Phase 2 — baseline coverage + mutation before
any test change. Issue #536, Slice 3.

Ported from tests/skills/test_improve_phase_2_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import grep, section
from skill_include_resolver import (
    resolve_test_improve_text as _text,
)


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


def test_phase_2_records_baseline_artifacts_under_tracked_data_slug():
    """Slice 4 Step 4.1 (plans/test-improve-baseline-persistence.md): both
    baseline artifacts land directly at the tracked data/ path, not under
    .claude/memory/."""
    s = _phase_2_section()
    assert grep(r"\.dev-team-reports/test-improve/<slug>/data/baseline-coverage\.json", s)
    assert grep(r"\.dev-team-reports/test-improve/<slug>/data/baseline-mutation\.json", s)


def test_phase_2_baseline_write_is_unconditional_not_report_opt_in_gated():
    """#1412: knob-7 is gone — Phase 2's own baseline write is a single,
    unconditional path (/coverage-baseline's canonical tracked-data/ write,
    itself untouched since Slice 1); no report-opt-in branching remains at
    Phase 2."""
    s = _phase_2_section()
    assert grep(r"unconditional", s, ignore_case=True)
    assert grep(r"\.dev-team-reports/test-improve/<slug>/data/baseline-coverage\.json", s)
    assert not grep(r"report opt-in|knob-7", s, ignore_case=True)


def test_phase_2_no_longer_defers_a_tracked_data_copy_to_phase_9():
    """Slice 4 Step 4.1: the baseline write is direct and atomic at capture
    time — there is no separate, later copy step, so Phase 2's own text no
    longer mentions Phase 9 at all."""
    s = _phase_2_section()
    assert not grep(r"Phase 9", s)
    assert grep(r"directly and atomic", s, ignore_case=True)
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


# --- Slice 4 Step 4.1: mutation-baseline existing-baseline guard -----------


def test_phase_2_mutation_guard_cites_the_shared_decision_defaults_axis():
    s = _phase_2_section()
    assert grep(r"existing-baseline guard", s, ignore_case=True)
    assert grep(r"knowledge/decision-defaults\.md", s)
    assert "Re-capture" in s


def test_phase_2_mutation_guard_reused_baseline_reporting_parity():
    s = _phase_2_section()
    assert grep(r"report its `captured_at`", s)
    assert grep(r"reporting parity", s, ignore_case=True)


def test_phase_2_mutation_guard_names_unrecognized_answer_reprompts_branch():
    s = _phase_2_section()
    assert grep(r"re-prompt", s, ignore_case=True)


def test_phase_2_mutation_guard_names_non_interactive_log_and_echo_branch():
    s = _phase_2_section()
    assert grep(r"log[[:space:]]+the[[:space:]]+auto-decision", s, ignore_case=True)
    assert grep(r"echo", s, ignore_case=True)


def test_phase_2_mutation_guard_malformed_file_treated_as_absent():
    s = _phase_2_section()
    assert grep(r"malformed|corrupt", s, ignore_case=True)
    assert grep(r"treat.*as absent", s, ignore_case=True)


def test_phase_2_never_uses_the_reserved_existing_copy_guard_term():
    # "existing-copy guard" is reserved for the Phase-9 mechanism Step 4.4
    # removes, so the two terms don't collide.
    assert "existing-copy guard" not in _phase_2_section()
