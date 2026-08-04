"""Contract for /test-improve's coverage-driven targeting (epic #1785).

Three Pass-1 targeting gaps found in the nextgen-core retrospective, all
landing in the same phase logic:

- #1786 — Phase 1/4 targeting comes from the per-module coverage breakdown
  Phase 2 computes, not from mutation survivors (a survivor can only exist on
  an already-covered line, so survivor ordering steers away from the
  0%-covered layers that hold the missing coverage).
- #1787 — a coverage-% goal that is structurally unreachable under the current
  refactor mode surfaces as an explicit choice at Phase 0, not as a silently
  waived gate discovered in the final report.
- #1790 — per-Story coverage deltas steer Phase 5 live; several consecutive
  near-zero-delta Stories are flagged mid-phase.

Static greps over shipped SKILL.md prose plus existence checks on the two
gate scripts the prose invokes — no git or state-mutating operations.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"
RANKING_SCRIPT = PLUGIN_ROOT / "scripts" / "coverage_gap_ranking.py"

RANKING_ARTIFACT = (
    r"\.dev-team-reports/test-improve/<slug>/data/coverage-gap-ranking\.json"
)


def _text() -> str:
    return SKILL.read_text()


def _phase(n: int) -> str:
    return section(_text(), rf"^### Phase {n}")


def _flat(n: int) -> str:
    """Phase `n`'s section with every whitespace run collapsed to one space,
    so a phrase hard-wrapped across markdown lines still matches a
    single-line pattern (the `collapsed()` precedent in skill_doc_helpers)."""
    return collapsed(_phase(n))


# ---------------------------------------------------------------------------
# the gate scripts exist and are invoked by plugin-root-relative path
# ---------------------------------------------------------------------------


def test_coverage_gap_ranking_script_ships():
    assert RANKING_SCRIPT.is_file()


def test_ranking_script_is_invoked_via_plugin_root():
    assert grep(
        r"\$\{CLAUDE_PLUGIN_ROOT\}/scripts/coverage_gap_ranking\.py", _text()
    )


# ---------------------------------------------------------------------------
# #1786 — Phase 2 computes the ranking
# ---------------------------------------------------------------------------


def test_phase_2_computes_the_coverage_gap_ranking_after_the_baseline():
    s = _phase(2)
    assert grep(r"coverage_gap_ranking\.py", s)
    assert grep(RANKING_ARTIFACT, s)


def test_phase_2_ranks_buckets_by_uncovered_lines_descending():
    assert grep(r"\*\*uncovered lines descending\*\*", _flat(2))


def test_phase_2_ranking_runs_in_every_mutation_mode():
    """The ranking is not gated on the mutation knob — it is the coverage
    targeting input, independent of whether mutation work happens at all."""
    assert grep(r"every mutation mode", _flat(2))


def test_phase_2_ranking_names_the_seam_classification():
    s = _phase(2)
    assert grep(r"`established`", s)
    assert grep(r"`absent`", s)


def test_phase_2_ranking_excludes_mutation_survivors_as_an_input():
    s = _flat(2)
    assert grep(r"[Mm]utation survivors are not an input to this ranking", s)
    assert grep(
        r"surviving mutant can only exist on a line a test already executes",
        s,
        ignore_case=True,
    )


def test_phase_2_ranking_writes_atomically_to_tracked_data():
    assert grep(r"temp-file-then-rename", _phase(2))


def test_phase_2_unparseable_report_is_not_a_clean_ranking():
    """Exit 2 must be surfaced and resolved, never papered over by falling
    back to survivor ordering."""
    s = _flat(2)
    assert grep(r"[Ee]xit 2", s)
    assert grep(r"not a clean ranking", s)
    assert grep(r"found nothing to rank", s)
    assert grep(r"[Dd]o not proceed with mutation survivors as a stand-in", s)


# ---------------------------------------------------------------------------
# #1787 — the goal conflict surfaces at Phase 0
# ---------------------------------------------------------------------------


def test_phase_0_has_a_coverage_target_vs_refactor_mode_conflict_check():
    s = _flat(0)
    assert grep(r"coverage_gap_ranking\.py", s)
    assert grep(r"#1787", s)


def test_phase_0_conflict_check_names_the_two_knobs_that_collide():
    """The conflict is between a stated coverage percentage (knob 4) and
    refactor-mode no-refactor (knob 3) — both must be named, or the check
    reads as a generic warning."""
    s = _flat(0)
    assert grep(r"knob 4", s)
    assert grep(r"knob 3", s)
    assert grep(r"`no-refactor`", s)


def test_phase_0_conflict_check_explains_why_mutation_work_cannot_close_it():
    assert grep(
        r"mutation-kill work cannot raise line or branch coverage on code that has no tests",
        _flat(0),
        ignore_case=True,
    )


def test_phase_0_conflict_offers_waive_switch_continue_not_a_silent_proceed():
    s = _flat(0)
    assert grep(r"\[w/s/c\]", s)
    assert grep(r"\[w\] waive the target", s)
    assert grep(r"\[s\] switch to refactor-allowed", s)
    assert grep(r"\[c\] continue as-is", s)


def test_phase_0_conflict_prompt_names_the_scripts_own_numbers():
    """The choice is presented with the arithmetic behind it, not as a
    judgement call: lines needed vs. lines reachable without new seams."""
    s = _flat(0)
    assert grep(r"`lines_needed`", s)
    assert grep(r"`reachable_uncovered_lines`", s)
    assert grep(r"seam-blocked", s)


def test_phase_0_conflict_is_resolved_before_work_starts_not_waived_later():
    s = _flat(0)
    assert grep(r"before\*\* any work starts", s) or grep(
        r"before any work starts", s
    )
    assert grep(r"never by waiving a gate later", s, ignore_case=True)


def test_phase_0_non_interactive_run_does_not_pick_a_stance():
    s = _flat(0)
    assert grep(r"coverage_target_conflict: unresolved", s)
    assert grep(r"does not silently pick a stance", s, ignore_case=True)


def test_phase_0_without_a_discoverable_report_defers_rather_than_guessing():
    s = _flat(0)
    assert grep(r"coverage_target_conflict: deferred", s)
    assert grep(r"do \*\*not\*\* fabricate a verdict", s, ignore_case=True)


def test_phase_0_deferred_check_is_never_first_surfaced_in_the_final_report():
    assert grep(
        r"never first surfaced in the Phase-9\s*report",
        _flat(0),
        ignore_case=True,
    )


def test_phase_0_clean_verdict_records_no_conflict():
    assert grep(r"coverage_target_conflict: none", _flat(0))


def test_phase_2_resolves_a_deferred_conflict_before_phase_1_runs():
    s = _flat(2)
    assert grep(r"coverage_target_conflict: deferred", s)
    assert grep(r"before Phase 1\s*runs", s, ignore_case=True)


def test_phase_2_deferred_switch_answer_respects_phase_0_immutability():
    """Phase-0 answers are immutable for the run, so `[s]` at Phase 2 stops
    and asks for a fresh refactor-allowed invocation — it never rewrites
    refactor-mode in phase-0.md mid-run."""
    s = _flat(2)
    assert grep(r"\[s\] stop and re-run in refactor-allowed mode", s)
    assert grep(r"immutab", s, ignore_case=True)
    assert grep(r"never rewrite `refactor-mode`", s, ignore_case=True)


# ---------------------------------------------------------------------------
# #1786 — Phase 1 and Phase 4 consume the ranking
# ---------------------------------------------------------------------------


def test_phase_1_orders_the_plan_by_the_ranking_when_a_coverage_target_is_stated():
    assert grep(RANKING_ARTIFACT, _phase(1))
    assert grep(
        r"coverage percentage is a stated goal", _flat(1), ignore_case=True
    )


def test_phase_1_does_not_order_by_mutation_survivor_count():
    assert grep(r"not by mutation survivor count", _flat(1), ignore_case=True)


def test_phase_1_scopes_mutation_survivors_to_already_seamed_modules():
    s = _flat(1)
    assert grep(
        r"survivors order work \*within\* an already-seamed module, never across modules",
        s,
    )
    assert grep(r"`seam: established`", s)
    assert grep(r"`seam: absent`", s)


def test_phase_1_ranking_is_informational_when_no_coverage_target_is_stated():
    assert grep(
        r"no coverage percentage is a stated goal.{0,200}informational",
        _flat(1),
        ignore_case=True,
    )


def test_phase_4_story_order_follows_the_ranking():
    s = _flat(4)
    assert grep(r"coverage-gap-ranking\.json", s)
    assert grep(
        r"rank order.{0,120}highest uncovered-line bucket first",
        s,
        ignore_case=True,
    )


def test_phase_4_does_not_let_issues_from_assessment_rederive_the_order():
    assert grep(
        r"does not re-derive an order of its own", _flat(4), ignore_case=True
    )
