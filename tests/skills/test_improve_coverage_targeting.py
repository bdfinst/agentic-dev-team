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
