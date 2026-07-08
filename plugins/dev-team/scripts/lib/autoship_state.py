"""autoship_state — shared round-state helpers for /dev-team:autoship (#989).

Timestamp formatting and staleness predicate shared by `autoship_discover.py`
and `autoship_reclaim.py`, so both scripts agree on what "stale" means
without either inspecting the other's code.

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
from datetime import datetime


def format_round_timestamp(dt: datetime) -> str:
    """Format `dt` as an ISO-8601 UTC string ending in "Z".

    Matches the timestamp shape already used in `metrics/config-changelog.jsonl`.
    """
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_stale(labeled_at: datetime, stale_after_hours: float, now: datetime) -> bool:
    """True when `labeled_at` is at or beyond `stale_after_hours` before `now`.

    Inclusive at the boundary: exactly `stale_after_hours` counts as stale —
    "past" in the issue's own language means "at or beyond".
    """
    elapsed_hours = (now - labeled_at).total_seconds() / 3600
    return elapsed_hours >= stale_after_hours


def _iso8601(raw: str) -> datetime:
    """`argparse` `type=` validator for an ISO-8601 timestamp string."""
    return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")


def positive_float_validator(flag_name: str):
    """Return an `argparse` `type=` validator that rejects `<= 0` for `flag_name`.

    Shared by `autoship_discover.py`'s `--max-cost-usd` and
    `autoship_reclaim.py`'s `--stale-after-hours` so both fail loud at the
    CLI boundary the same way, per `evals/code-review-benchmark/cli.py`'s
    `_positive_float` precedent — one implementation instead of two
    independently-copied ones.
    """

    def _validator(raw: str) -> float:
        value = float(raw)
        if value <= 0:
            raise argparse.ArgumentTypeError(
                f"{flag_name} must be a positive number, got {raw!r}"
            )
        return value

    return _validator


def add_input_seam_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared `--input-file`/`--now-override` test seam to `parser`.

    Both flags are optional at this shared level; each caller decides its
    own default file-source behavior. `--input-file` lets a caller skip its
    live `gh` fetch entirely (JSON array of issue objects); `--now-override`
    feeds `is_stale` an explicit "now" instead of the real clock.
    """
    parser.add_argument(
        "--input-file",
        help="Path to a JSON array of issue objects, bypassing the live gh fetch.",
    )
    parser.add_argument(
        "--now-override",
        type=_iso8601,
        help="ISO-8601 UTC timestamp (e.g. 2026-07-08T12:00:00Z) to use as 'now'.",
    )
