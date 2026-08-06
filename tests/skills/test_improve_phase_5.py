"""Contract for /test-improve Phase 5 — improve tests without refactoring,
then end-of-phase review loop. Issue #536, Slice 6 (Steps 6.1 + 6.2).

Ported from tests/skills/test_improve_phase_4_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import grep, section
from skill_include_resolver import resolve_test_improve_text as _text


def _phase_5_section() -> str:
    return section(_text(), r"^### Phase 5( —|$| \()")


def test_body_contains_a_phase_5_section_header():
    assert grep(r"^### Phase 5( —|$| \()", _text())


# Step 6.1 assertions — build + mutation-kill loop


def test_phase_5_invokes_build():
    assert grep(r"/build", _phase_5_section())


def test_phase_5_inherits_no_refactor_mode_from_phase_0():
    assert grep(
        r"no-refactor.*(Phase[[:space:]]+0|inherit)|inherit.*no-refactor|"
        r"Phase[[:space:]]+0.*no-refactor",
        _phase_5_section(),
        ignore_case=True,
    )


def test_phase_5_measures_per_story_coverage_via_coverage_delta():
    assert grep(
        r"/coverage-delta.*--workflow[[:space:]]+test-improve.*--story|"
        r"--story.*--workflow[[:space:]]+test-improve.*coverage-delta",
        _phase_5_section(),
    )


def test_phase_5_coverage_delta_appends_to_the_tracked_data_path():
    """Slice 4 Step 4.2 (plans/test-improve-baseline-persistence.md):
    coverage-history.json lives at the tracked data/ path, not
    .claude/memory/."""
    assert grep(
        r"\.dev-team-reports/test-improve/<slug>/data/coverage-history\.json",
        _phase_5_section(),
    )


def test_phase_5_invokes_the_mutation_kill_agent_per_story_with_file_and_max_rounds_3():
    s = _phase_5_section()
    assert grep(r"mutation-kill", s, ignore_case=True)
    assert grep(r"--file", s)
    assert grep(r"--max-rounds 3", s)


def test_phase_5_documents_the_c_r_w_q_mutation_kill_prompt():
    assert grep(r"\[c/r/w/q\]|\[c\].*\[r\].*\[w\].*\[q\]", _phase_5_section())


def test_phase_5_mutation_kill_runs_in_killloop_and_baseline_modes_not_off():
    """#1126: the Phase-5 mutant-kill loop runs in both `kill-loop` and
    `baseline+kill-loop`, and is skipped when mutation mode is `off`."""
    s = _phase_5_section()
    assert grep(r"`kill-loop`", s)
    assert grep(r"`baseline\+kill-loop`", s)
    assert grep(r"skip.*`off`|`off`.*skip", s, ignore_case=True)


def test_phase_5_mutation_kill_is_advisory_on_go_no_commit():
    assert grep(
        r"Go.*(advisory|no[[:space:]]+commit|logged)|advisory.*Go",
        _phase_5_section(),
        ignore_case=True,
    )


def test_phase_5_applies_binding_mode_annotations_per_phase_0():
    assert grep(
        r"Given/When/Then|leading[[:space:]]+comment|scenario[[:space:]]+name",
        _phase_5_section(),
        ignore_case=True,
    )


# Step 6.2 assertions — end-of-phase review loop


def test_phase_5_review_loop_dispatches_test_design_since_and_code_review_since_in_parallel():
    s = _phase_5_section()
    assert grep(r"/test-design[[:space:]]+--since", s)
    assert grep(r"/code-review[[:space:]]+--since", s)
    assert grep(r"parallel|concurrent|dispatch", s, ignore_case=True)


def test_phase_5_review_loop_runs_apply_fixes_corrections_then_re_runs_code_review():
    assert grep(r"/apply-fixes[[:space:]]+corrections/", _phase_5_section())


def test_phase_5_review_loop_caps_at_2_iterations_before_escalation():
    assert grep(
        r"2[[:space:]]+iteration|max[[:space:]]+2|at[[:space:]]+most[[:space:]]+2",
        _phase_5_section(),
        ignore_case=True,
    )


def test_phase_5_review_loop_uses_r_w_q_escalation_prompt():
    assert grep(r"\[r/w/q\]|\[r\].*\[w\].*\[q\]", _phase_5_section())


def test_phase_5_review_loop_writes_phase_5_review_json_with_fixed_schema():
    s = _phase_5_section()
    assert grep(r"memory/test-improve/<slug>/phase-5-review\.json", s)
    assert grep(r"base_sha", s)
    assert grep(r"head_sha", s)
    assert grep(r"farley_score", s)
    assert grep(r"smells", s)
    assert grep(r"code_review", s)
    assert grep(r"iterations", s)
    assert grep(r"escalated", s)


def test_phase_5_review_loop_writes_waivers_json_tagged_with_findings():
    s = _phase_5_section()
    assert grep(r"memory/test-improve/<slug>/waivers\.json", s)
    assert grep(r"tag", s, ignore_case=True)
