#!/usr/bin/env python3
"""churn_recurrence — commit-gap session-boundary heuristic (issue #2039).

Sibling module to `scripts/churn_coupling_report.py`, split out per the
plan's design note so the second, unrelated responsibility (cross-session
churn recurrence) doesn't grow that 735-line script into a god object.
`churn_coupling_report.py` -> `churn_recurrence.py` is the only allowed
import direction: this module never imports the `Commit` dataclass, and
takes plain `(sha, timestamp)` tuples or `{"sha", "timestamp"}` dicts
instead, matching this repo's `scripts/lib/` convention of taking plain
dict/list input rather than a caller-defined dataclass (see
`apply_severity_floors.py`).

No transcript data is available to this script, so "session" here is a
**commit-timestamp-gap proxy**, never the transcript-derived `session_id`
concept `session_extract.py` owns. To keep that distinction visible at every
call site, this module deliberately never uses the bare word "session" for
its own concept -- it is always `commit_session`.
"""
from __future__ import annotations

from datetime import datetime, timedelta

#: Default gap, in hours, above which two chronologically-adjacent commits
#: touching the same file are treated as separate commit-sessions rather
#: than one continuous editing session.
DEFAULT_COMMIT_GAP_HOURS = 4.0


def _normalize(commit) -> tuple[str, str]:
    """Read a `(sha, timestamp)` tuple or `{"sha", "timestamp"}` dict.

    Deliberately does not accept `churn_coupling_report.Commit` -- accepting
    that type here would create a two-way import dependency between the two
    modules.
    """
    if isinstance(commit, dict):
        return str(commit.get("sha", "")), str(commit.get("timestamp", ""))
    sha, timestamp = commit
    return str(sha), str(timestamp)


def partition_commit_sessions(
    commits, commit_gap_hours: float = DEFAULT_COMMIT_GAP_HOURS
) -> list[list[dict[str, str]]]:
    """Partition one file's commits into commit-session groups.

    `commits` is a list of `(sha, timestamp)` tuples or `{"sha",
    "timestamp"}` dicts for a single file, with `timestamp` an ISO 8601
    string (the shape `churn_coupling_report.Commit.timestamp` carries,
    e.g. git's `%aI` author-date format). Input is expected to be
    chronologically sorted already; this function re-sorts ascending by
    timestamp regardless, so partitioning is correct even if the caller's
    ordering discipline is wrong -- a sorted input simply sorts to itself.

    Returns a list of commit-session groups, each a list of `{"sha",
    "timestamp"}` dicts in ascending-time order. Two chronologically
    adjacent commits start a new commit-session when the gap between them
    is **greater than or equal to** `commit_gap_hours` -- an inclusive
    boundary, matching `churn_coupling_report.py`'s existing `--max-commits`
    inclusive-boundary convention (`len(commits) >= args.max_commits`). A
    gap strictly less than the threshold keeps both commits in the same
    commit-session.
    """
    if not commits:
        return []

    normalized = sorted(
        (_normalize(commit) for commit in commits),
        key=lambda pair: datetime.fromisoformat(pair[1]),
    )

    threshold = timedelta(hours=commit_gap_hours)
    sessions: list[list[dict[str, str]]] = [
        [{"sha": normalized[0][0], "timestamp": normalized[0][1]}]
    ]
    previous_ts = datetime.fromisoformat(normalized[0][1])

    for sha, ts_str in normalized[1:]:
        ts = datetime.fromisoformat(ts_str)
        if ts - previous_ts >= threshold:
            sessions.append([{"sha": sha, "timestamp": ts_str}])
        else:
            sessions[-1].append({"sha": sha, "timestamp": ts_str})
        previous_ts = ts

    return sessions
