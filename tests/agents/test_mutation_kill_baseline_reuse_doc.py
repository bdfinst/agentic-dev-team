"""Doc-content contract for the mutation-kill agent's baseline-reuse
procedure (Slice 3, Step 3.2, #1545).

Mirrors the grep-on-section pattern already used in
tests/agents/test_mutation_kill_agent.py (see its `feasibility_section`/
`feasibility_flat` fixtures) — pure text assertions over shipped agent
prose, no state-mutating filesystem/git operations. Reuses
`skill_doc_helpers.section()` for section-scoped extraction rather than
hand-rolling a new one, per this repo's established DRY convention.
"""

from __future__ import annotations

import re

import pytest
from _mutation_kill_agent_doc_helpers import agent_text, required_section
from skill_doc_helpers import collapsed


@pytest.fixture(scope="module")
def text() -> str:
    return agent_text()


@pytest.fixture(scope="module")
def flat(text: str) -> str:
    return collapsed(text)


@pytest.fixture(scope="module")
def reuse_section(text: str) -> str:
    return required_section(
        text,
        r"^## Baseline reuse for Round 1",
        boundary_pattern=r"^## ",
        include_start_line=False,
        name="Baseline reuse for Round 1",
    )


@pytest.fixture(scope="module")
def reuse_flat(reuse_section: str) -> str:
    return collapsed(reuse_section)


# --- (a) + (b): canonical baseline and tracking-file paths ------------------


def test_canonical_baseline_report_path_documented(reuse_section: str) -> None:
    assert "StrykerOutput/baseline/reports/mutation-report.json" in reuse_section


def test_tracking_file_path_documented(reuse_section: str) -> None:
    assert "StrykerOutput/mutation-kill-baseline-consumption.json" in reuse_section


# --- (c): the resolve-before / mark-consumed-immediately-after procedure ----


def test_resolve_runs_before_round_1_named_per_file(reuse_section: str) -> None:
    assert "mutation_baseline_reuse.py resolve" in reuse_section
    assert re.search(r"before that file'?s Round 1", reuse_section, re.IGNORECASE)


def test_eligible_true_seeds_round_1_via_report_flag(
    reuse_section: str, reuse_flat: str
) -> None:
    assert "eligible: true" in reuse_section
    assert re.search(r"--report <abs-baseline-report-path>", reuse_flat)
    assert re.search(r"instead of a\s+fresh scoped run", reuse_flat)


def test_ineligible_file_runs_fresh_unchanged(reuse_flat: str) -> None:
    assert re.search(
        r"eligible: false.*Round 1 runs fresh, unchanged from today", reuse_flat
    )


def test_mark_consumed_runs_immediately_after_round_per_file_not_batched(
    reuse_section: str, reuse_flat: str
) -> None:
    assert "mutation_baseline_reuse.py mark-consumed" in reuse_section
    assert re.search(
        r"immediately after that file'?s round concludes", reuse_flat, re.IGNORECASE
    )
    assert re.search(r"per file, not batched", reuse_flat, re.IGNORECASE)


# --- mark-consumed failure is checked and surfaced, never silently absorbed -


def test_mark_consumed_success_field_checked_and_failure_warned(
    reuse_section: str, reuse_flat: str
) -> None:
    assert re.search(r"`success`\s+field", reuse_flat)
    assert "success: false" in reuse_section
    assert re.search(
        r"operator-visible\s+warning naming the file and the `error` reason",
        reuse_flat,
    )
    assert re.search(r"before continuing to the next\s+file", reuse_flat)
    assert re.search(
        r"never silently absorbed into a\s+successful-looking summary", reuse_flat
    )


# --- (d): capture commit captured once, held only for this invocation -------


def test_capture_commit_recorded_once_and_held_for_this_invocation_only(
    reuse_flat: str,
) -> None:
    assert re.search(r"git rev-parse HEAD", reuse_flat)
    assert re.search(
        r"hold it only for\s+the rest of this invocation", reuse_flat, re.IGNORECASE
    )
    assert re.search(r"not persisted to a\s+separate file", reuse_flat, re.IGNORECASE)


# --- (e): no baseline report present -> every file's Round 1 runs fresh -----


def test_no_baseline_report_skips_resolve_entirely(reuse_flat: str) -> None:
    assert re.search(
        r"No baseline report at the canonical path.{0,20}skip `resolve` entirely",
        reuse_flat,
    )
    assert re.search(
        r"every\s+file's Round 1 runs fresh, exactly as today", reuse_flat
    )


# --- (f): the three-counter run-summary line ---------------------------------


def test_run_summary_reports_seeded_ran_fresh_mark_failed(reuse_section: str) -> None:
    assert "baseline: seeded N, ran-fresh M, mark-failed K" in reuse_section


# --- (g): widened scope, all --concurrency values ----------------------------


def test_heading_states_all_concurrency_values(text: str) -> None:
    assert "## Baseline reuse for Round 1 (all `--concurrency` values)" in text


def test_feature_scoped_to_all_concurrency_values(reuse_flat: str) -> None:
    assert re.search(r"Scope: all\s+`--concurrency` values", reuse_flat)
    assert re.search(
        r"resolves\s+the baseline report and the tracking file at the main "
        r"checkout's\s+absolute path",
        reuse_flat,
    )
    assert re.search(r"git rev-parse --show-toplevel", reuse_flat)
    assert re.search(
        r"`resolve`/`mark-consumed`.{0,5}never join\s+`--tracking`/`--report` "
        r"relative to the script'?s own location",
        reuse_flat,
    )


# --- (h): the ran-fresh tally no longer lists --concurrency as a standalone -
# --- reason -------------------------------------------------------------------


def test_ran_fresh_tally_no_longer_lists_concurrency_as_a_reason(
    reuse_flat: str,
) -> None:
    assert re.search(
        r"`ran-fresh`\s+counts every file whose\s+Round 1 ran fresh \(no "
        r"baseline present, or\s+ineligible\), and `mark-failed`",
        reuse_flat,
    )
    assert "--concurrency >1" not in reuse_flat


# --- (i): absolute-path invocation guidance + concurrent-write safety -------


def test_invocation_guidance_requires_absolute_tracking_and_report_paths(
    reuse_flat: str,
) -> None:
    assert re.search(
        r"must be\s+the main checkout's absolute path", reuse_flat
    )
    assert re.search(
        r"not\s+`StrykerOutput/mutation-kill-baseline-consumption\.json`\s+relative "
        r"to the current",
        reuse_flat,
    )
    assert re.search(
        r"<abs-baseline-report-path>.{0,400}must be the main checkout's absolute path",
        reuse_flat,
        re.DOTALL,
    )


def test_concurrent_mark_consumed_calls_documented_as_safe(reuse_flat: str) -> None:
    assert re.search(
        r"mark-consumed.{0,40}calls from concurrent worktrees are\s+now\s+"
        r"interprocess-locked",
        reuse_flat,
    )
    assert re.search(r"atomic_state\.locked_state\(strict=True\)", reuse_flat)
    assert re.search(
        r"safe to run without\s+agent-side serialization", reuse_flat
    )


def test_lock_residual_risk_does_not_cover_same_file_double_resolve(
    reuse_flat: str,
) -> None:
    """The lock protects the tracking file's write integrity across
    *different* files, not double-resolve of the SAME file from two workers
    concurrently — that residual risk must be stated explicitly, not left
    implicit (#1920)."""
    assert re.search(
        r"protects the tracking file's write integrity", reuse_flat
    )
    assert re.search(
        r"not double-resolve of\s+the same file from two workers concurrently",
        reuse_flat,
    )
    assert re.search(
        r"each file must still be\s+assigned to exactly one worker per run",
        reuse_flat,
    )


# --- Whole-file sweep: no stale --concurrency 1-only restriction remains ----


def test_no_concurrency_1_only_restriction_remains_anywhere(text: str) -> None:
    """No baseline-reuse `--concurrency 1`-only restriction phrasing survives
    anywhere in the full document — not just the Baseline reuse section."""
    assert "--concurrency 1" not in text
    assert "--concurrency >1" not in text
    assert "--concurrency > 1" not in text


# --- Whole-file sweep: no stale --from-report flag name remains -------------


def test_no_occurrence_of_from_report_flag_remains(text: str) -> None:
    assert "--from-report" not in text


def test_invocation_section_names_report_flag(text: str) -> None:
    # include_start_line=False here normalizes with every other required_section()
    # call site in this file group (all pass False) -- the original hand-rolled
    # skill_doc_helpers.section call relied on its own include_start_line=True
    # default, dropping the "## Invocation" heading line here is confirmed inert
    # since neither assertion below checks that line.
    invocation = required_section(
        text,
        r"^## Invocation",
        boundary_pattern=r"^## ",
        include_start_line=False,
        name="Invocation",
    )
    assert "--report <path>" in invocation
    assert "--from-report" not in invocation
