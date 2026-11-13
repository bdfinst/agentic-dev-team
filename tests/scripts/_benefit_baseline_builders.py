"""Builders and assertions shared by the benefit baseline test files.

A synthetic ``Context`` starts from the real entries (so thresholds and ``minimum_n`` come from the
pre-registration) with a valid cell for each metric's pinned status. Named without a leading ``test_`` so
pytest does not collect it.
"""

from __future__ import annotations

import copy

from _benefit_baseline_rules import (
    ALLOWED_TOKENS,
    ISSUE_CITES,
    NO_VERDICT_STATUSES,
    PINNED_STATUS,
    Context,
    cell_token,
    check_baseline_cells,
    check_issue_cites,
    check_measured_cells,
    check_records,
    check_unmeasurable_matches_handling,
    problems_for,
)
from _benefit_eval_support import real_entries

GUARD_FP = "guard-false-positive"
CELL_CHECKS = (check_baseline_cells, check_unmeasurable_matches_handling, check_issue_cites)
RECORD_CHECKS = (check_measured_cells, check_records)


def good_baseline(metric_id: str) -> str:
    """A valid cell for the metric's pinned status; a measured metric starts as not-yet-run."""
    status = PINNED_STATUS[metric_id]
    head = (
        "no-reference: not-yet-run; replay pending"
        if status == "measured"
        else f"{status}: reference text"
    )
    cite = ISSUE_CITES.get(metric_id)
    return f"{head} (#{cite})" if cite else head


def good_entries() -> dict[str, dict]:
    """The real entries, so thresholds and `minimum_n` come from the pre-registration, with valid cells."""
    entries = copy.deepcopy(real_entries())
    for metric_id, entry in entries.items():
        entry["baseline"] = good_baseline(metric_id)
    return entries


def good_doc(entries: dict[str, dict]) -> str:
    """A minimal document with a status table and a verdict-order paragraph that agree with the cells."""
    ids = ", ".join(
        f"`{m}`"
        for m, entry in entries.items()
        if cell_token(entry) in NO_VERDICT_STATUSES
    )
    return (
        table_doc(ALLOWED_TOKENS)
        + "## Rules\n\n**Verdict order.** Evaluate retire first. "
        f"No keep, tune, or retire verdict is posted for: {ids}.\n\n**Within and breach.** Text.\n"
    )


def table_doc(tokens) -> str:
    rows = "\n".join(f"| `{token}` | meaning |" for token in tokens)
    return f"## Baseline status\n\n| Status | Meaning |\n| --- | --- |\n{rows}\n\n"


def ctx_for(entries=None, **overrides) -> Context:
    entries = entries if entries is not None else good_entries()
    overrides.setdefault("doc_text", good_doc(entries))
    return Context(entries=entries, **overrides)


def with_baseline(metric_id: str, cell: str, **overrides) -> Context:
    entries = good_entries()
    entries[metric_id]["baseline"] = cell
    return ctx_for(entries, **overrides)


def assert_clean(ctx: Context, *checks) -> None:
    problems = problems_for(ctx, *checks)
    assert not problems, "\n".join(problems)


def assert_rejected(ctx: Context, *checks, starts: str, has=()) -> None:
    """Some problem starts with `starts` and the problems starting so mention every fragment in `has`."""
    problems = problems_for(ctx, *checks)
    hits = [problem for problem in problems if problem.startswith(starts)]
    assert hits, f"no problem starts with {starts!r}: {problems}"
    for fragment in has:
        assert any(fragment in hit for hit in hits), (
            f"{fragment!r} is in none of {hits}"
        )

