"""autoship_state — shared round-state helpers for /dev-team:autoship (#989).

Timestamp formatting and staleness predicate shared by `autoship_discover.py`
and `autoship_reclaim.py`, so both scripts agree on what "stale" means
without either inspecting the other's code.

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

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
