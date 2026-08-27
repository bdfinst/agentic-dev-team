"""Doc-content contract for the Stryker-side mechanics of the mutation-kill
agent's opt-in ``--skip-static-mutants`` flag (#1907, Slice 2, Step 2.2 of
plans/mutation-kill-batch-hardening-1906-1910.md).

Sibling to ``tests/agents/test_mutation_kill_skip_static_doc.py`` (Step 2.1),
which covers only the flag's bare presence/default/scope/link in
``mutation-kill.md``'s Invocation bullet. This file covers everything else
— mechanism, the corrected trade-off, the unfiltered-scoring invariant, the
absent-field fallback, and the non-JS/TS/``--headless``/``--parallel`` scope
notes — all of which now live in ``javascript-stryker.md``'s dedicated
"### Static-mutant skip" subsection rather than the whole "## Run (scoped)"
section (test-review + correctness-review finding, build round 1,
addressed: assertions are windowed to that subsection specifically, not the
enclosing section, mirroring ``test_mutation_testing_skill_doc.py``'s
``_emitting_adapters_window()``/``_line_clustering_window()`` precedent).

Pure text assertions over shipped skill-reference prose, no state-mutating
filesystem/git operations — same convention as
``tests/skills/test_mutation_testing_scoping.py``.
"""

from __future__ import annotations

import re

import pytest
from skill_doc_helpers import PLUGIN_ROOT, collapsed, section

JS_STRYKER = (
    PLUGIN_ROOT
    / "skills"
    / "mutation-testing"
    / "references"
    / "languages"
    / "javascript-stryker.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return JS_STRYKER.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def static_skip_section(text: str) -> str:
    result = section(
        text,
        r"^### Static-mutant skip",
        boundary_pattern=r"^#{2,3} ",
        include_start_line=False,
    )
    assert result, "Static-mutant skip subsection not found"
    return result


@pytest.fixture(scope="module")
def static_skip_flat(static_skip_section: str) -> str:
    return collapsed(static_skip_section)


def test_flag_is_named_in_the_static_skip_subsection(static_skip_section: str) -> None:
    assert "--skip-static-mutants" in static_skip_section


def test_subsection_links_back_to_mutation_kill_invocation(static_skip_flat: str) -> None:
    assert "agents/mutation-kill.md#invocation" in static_skip_flat


def test_mechanism_cites_the_survivor_extraction_functions(
    static_skip_flat: str,
) -> None:
    """Step 1.5 (#1937): the inline "filter native mutant objects before
    normalization" mechanics description is retired — the filtering is a
    deterministic computation owned by mutation_report.py, cited here by
    name instead of re-derived in prose.

    Tightened (round-1 review, test-review finding): the three unanchored
    substring checks this test used to run independently could all stay
    green while the actual mechanism sentence was rewritten or removed, as
    long as the three names appeared anywhere else in the subsection. Now
    the first assertion requires `survivors_by_mutator`, `skip_static=True`,
    and `mutation_report.py` to co-occur in the actual mechanism clause; the
    second anchors the CLI invocation as one literal string, mirroring
    tests/agents/test_mutation_kill_line_clustering_doc.py's
    `mutation_report_cli.py --survivors-by-line` anchor."""
    assert re.search(
        r"survivors_by_mutator\(\.\.\.,\s*skip_static=True\).*?mutation_report\.py",
        static_skip_flat,
    )
    # ADR 0032/0033 (round-3 pre-merge review, #1937): the CLI invocation is
    # cited ${CLAUDE_PLUGIN_ROOT}-qualified and quoted, not bare.
    assert (
        '"${CLAUDE_PLUGIN_ROOT}/skills/mutation-testing/scripts/mutation_report_cli.py"'
        in static_skip_flat
    )
    assert "--survivors-by-mutator --skip-static" in static_skip_flat


def test_mechanism_explains_why_a_static_mutant_forces_a_full_suite_rerun(
    static_skip_flat: str,
) -> None:
    assert re.search(r"module-initialization time", static_skip_flat)
    assert re.search(r'coverageAnalysis:\s*"perTest"', static_skip_flat)
    assert re.search(r"forcing a full-suite re-run", static_skip_flat)


def test_trade_off_does_not_claim_stryker_runs_faster(static_skip_flat: str) -> None:
    """correctness-review finding, build round 1: the prior wording claimed
    'trades a smaller wall-clock (no full-suite re-run per static mutant)',
    which the post-run filter cannot deliver — Stryker has already paid
    that cost by the time the report exists. Pin the corrected framing.

    Re-pinned (plan #1940, Step 2.3): the trade-off used to be framed as a
    "small, documented survivor over-count" — but the over-count was never
    actually reflected in adjusted_score, so "documented" was misleading.
    That framing is retired in favor of "deferring ... rather than
    eliminating", now genuinely documented via accepted_static_survivors()
    (see test_adjusted_score_folds_in_accepted_static_survivors below)."""
    assert re.search(
        r"cannot make Stryker'?s own run faster", static_skip_flat
    )
    assert re.search(r"saves is the generation-and-verify.{0,10}rounds", static_skip_flat)
    assert re.search(r"deferring each skipped static mutant", static_skip_flat)


def test_scoring_and_convergence_stay_unfiltered(static_skip_flat: str) -> None:
    """correctness-review finding, build round 1: without this statement, a
    file whose only remaining survivors are static could have its filtered
    (empty) list feed the survivors == 0 convergence exit, getting written
    as status: "converged" and permanently glob-shrunk out of future --all
    runs — contradicting the doc's own "stays counted as an unaddressed
    survivor" promise."""
    assert re.search(r"convergence.{0,20}stay unfiltered", static_skip_flat)
    assert re.search(r"survivors == 0", static_skip_flat)
    assert re.search(r'never be written as `?status: "converged"`?', static_skip_flat)


def test_adjusted_score_folds_in_accepted_static_survivors(static_skip_flat: str) -> None:
    """Plan #1940, Slice 2, Step 2.3: adjusted_score now accounts for
    static-skipped mutants via mutation_report_cli.py's
    --accepted-static-survivors mode (added in Steps 2.1/2.2). This is a
    real-structure check, not a bag-of-words match — it anchors the CLI
    invocation, "fold", and adjusted_score inside one sentence/bullet so a
    doc edit that scatters the three words across unrelated sentences still
    fails."""
    assert re.search(
        r"--accepted-static-survivors[^.]*\bfold[^.]*adjusted_score",
        static_skip_flat,
    )
    # #1948 (resolved): clustering counts every survivor including static
    # ones — it never filtered, so there was nothing for --skip-static to
    # "touch." The doc now says so explicitly rather than describing an open
    # gap.
    assert re.search(r"[Cc]lustering.{0,60}counts every survivor", static_skip_flat)
    assert "#1948" in static_skip_flat


def test_skip_static_is_a_no_op_on_survivors_by_line_clustering(
    static_skip_flat: str,
) -> None:
    """#1948, Option A: survivors_by_line() now accepts skip_static, but the
    doc must say plainly that it does not filter the returned clusters — a
    static survivor still counts toward its line's cluster weight/ranking,
    since it's still evidence of that line's mutation density. Pins the
    resolution, not just the flag's bare existence."""
    assert re.search(
        r"survivors_by_line\(\).{0,40}accept.{0,10}skip_static", static_skip_flat
    )
    assert re.search(r"no-op", static_skip_flat)
    assert re.search(r"still counts toward its line'?s cluster weight", static_skip_flat)


def test_reconciliation_guidance_names_the_static_field_check(
    static_skip_flat: str,
) -> None:
    """#1948: the doc must tell the agent HOW to reconcile a
    clustered-but-unfiltered ranking with the filtered mutator-grouped
    generation list — checking each survivor's own `static` field before
    writing a test for it, and moving to the next cluster when every
    survivor in the top one is static."""
    assert re.search(r"check.{0,20}each survivor'?s own `?static`? field", static_skip_flat)
    assert re.search(r"move to the next cluster", static_skip_flat)


def test_absent_static_field_has_a_stated_fallback(static_skip_flat: str) -> None:
    assert re.search(r"[Ff]allback when the field is absent", static_skip_flat)
    assert re.search(r"skip is inapplicable", static_skip_flat)
    # #1937 closing-pass finding: the CLI (not the agent) owns detecting the
    # inapplicable case — pin the corrected ownership claim, not just the
    # surrounding phrases that were already true pre-fix.
    assert re.search(r"mutation_report_cli\.py --skip-static", static_skip_flat)
    assert re.search(
        r"not re-detect the inapplicable case itself", static_skip_flat
    )


def test_scope_is_interactive_agent_path_only(static_skip_flat: str) -> None:
    assert re.search(
        r"invocation.{0,20}flag on.{0,20}/mutation-kill.{0,20}itself is"
        r" agent-parsed prose, not an argparse flag",
        static_skip_flat,
    )
    assert re.search(r"unrecognized arguments", static_skip_flat)
    # #1937 closing-pass finding: pin the narrowing that makes the claim
    # above correct — the invocation flag is prose, but the filter
    # computation it drives is a real, shipped argparse flag.
    assert re.search(
        r"filter.{0,12}computation.{0,12}it drives is scripted",
        static_skip_flat,
    )


def test_parallel_fan_out_does_not_auto_propagate_the_flag(static_skip_flat: str) -> None:
    assert re.search(r"--all --parallel", static_skip_flat)
    assert re.search(r"does not propagate automatically", static_skip_flat)
