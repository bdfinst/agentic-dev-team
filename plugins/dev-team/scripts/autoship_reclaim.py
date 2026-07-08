#!/usr/bin/env python3
"""Reclaim issues orphaned by a crashed/interrupted /dev-team:autoship round (#989).

Relabels a stale `autoship:in-progress` issue back to `autoship:blocked` with
an explanatory comment, so a crashed or interrupted autoship round doesn't
leave an issue permanently stuck "in progress". Deterministic, testable
Python — no model judgment, per the epic's architecture rationale (see plan
`plans/issue-989-autoship-discovery-reclaim.md`, Slice 3).

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import autoship_state  # noqa: E402

IN_PROGRESS_LABEL = "autoship:in-progress"
BLOCKED_LABEL = "autoship:blocked"


def select_orphaned(issues: list, stale_after_hours: float, now: datetime) -> list:
    """Return the subset of `issues` that are orphaned in-progress issues.

    An issue qualifies when it is open, carries `autoship:in-progress`, and
    its `labeled_at` (falling back to `updatedAt` when `labeled_at` is
    absent — the live-fetch path's best-effort fallback, added in a later
    step) is stale per `autoship_state.is_stale` (inclusive boundary).
    """
    orphaned = []
    for issue in issues:
        if issue.get("state") != "OPEN":
            continue
        labels = issue.get("labels") or []
        label_names = {
            label["name"] if isinstance(label, dict) else label for label in labels
        }
        if IN_PROGRESS_LABEL not in label_names:
            continue
        timestamp_raw = issue.get("labeled_at") or issue.get("updatedAt")
        if timestamp_raw is None:
            continue
        labeled_at = _parse_timestamp(timestamp_raw)
        if autoship_state.is_stale(labeled_at, stale_after_hours, now):
            orphaned.append(issue)
    return orphaned


def _parse_timestamp(raw) -> datetime:
    """Parse a `labeled_at`/`updatedAt` value into a `datetime`.

    Accepts either an already-parsed `datetime` (as tests may supply) or an
    ISO-8601 string (as `--input-file` JSON and the live `gh` fetch supply),
    tolerating a trailing `Z` suffix.
    """
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(raw.rstrip("Z"))


def _positive_float(raw: str) -> float:
    """`argparse` `type=` validator for `--stale-after-hours`: rejects `<= 0`.

    Mirrors `evals/code-review-benchmark/cli.py`'s `_positive_float`
    validator for `--max-cost-usd` — fail loud at the CLI boundary rather
    than silently clamping downstream.
    """
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError(
            f"--stale-after-hours must be a positive number, got {raw!r}"
        )
    return value


def _build_parser() -> argparse.ArgumentParser:
    """Build this CLI's `argparse.ArgumentParser`, isolated from `main()` so
    tests can assert defaults/overrides via `_build_parser().parse_args([...])`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stale-after-hours",
        type=_positive_float,
        default=24,
        help=(
            "Hours an issue may stay autoship:in-progress before it is "
            "considered orphaned (default 24)."
        ),
    )
    autoship_state.add_input_seam_args(parser)
    return parser


if __name__ == "__main__":
    raise SystemExit(0)
