"""Unit tests for scripts/lib/churn_recurrence.py (issue #2039, Step 2.2b).

Pins the commit-gap session-boundary heuristic: `partition_commit_sessions`
groups a file's commits into `commit_session` groups by timestamp gap, with
an inclusive boundary (a gap exactly equal to `commit_gap_hours` starts a
new commit-session -- matching `churn_coupling_report.py`'s existing
`--max-commits` inclusive-boundary convention).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
import churn_recurrence as cr

_BASE = datetime(2026, 1, 5, 9, 0, 0, tzinfo=timezone.utc)


def _ts(hours: float) -> str:
    """ISO 8601 timestamp `hours` after the fixed base instant."""
    return (_BASE + timedelta(hours=hours)).isoformat()


def _commits(*specs):
    """Build `(sha, timestamp)` tuples from `(sha, hours_offset)` pairs."""
    return [(sha, _ts(hours)) for sha, hours in specs]


def _shas(sessions):
    """Flatten a partition result to `[[sha, ...], ...]` for easy asserts."""
    return [[c["sha"] for c in group] for group in sessions]


def test_single_commit_session_when_all_gaps_below_threshold():
    commits = _commits(("a", 0), ("b", 1), ("c", 2))

    sessions = cr.partition_commit_sessions(commits, commit_gap_hours=4)

    assert _shas(sessions) == [["a", "b", "c"]]


def test_multiple_commit_sessions_when_a_gap_exceeds_threshold():
    # a->b is 1h apart (below threshold); b->c is 5h apart (above threshold);
    # c->d is 1h apart (below threshold) -- two commit-sessions.
    commits = _commits(("a", 0), ("b", 1), ("c", 6), ("d", 7))

    sessions = cr.partition_commit_sessions(commits, commit_gap_hours=4)

    assert _shas(sessions) == [["a", "b"], ["c", "d"]]


def test_gap_exactly_at_threshold_starts_a_new_commit_session():
    commits = _commits(("a", 0), ("b", 4))

    sessions = cr.partition_commit_sessions(commits, commit_gap_hours=4)

    assert _shas(sessions) == [["a"], ["b"]]


def test_gap_just_under_threshold_stays_in_the_same_commit_session():
    commits = _commits(("a", 0), ("b", 3.99))

    sessions = cr.partition_commit_sessions(commits, commit_gap_hours=4)

    assert _shas(sessions) == [["a", "b"]]


def test_empty_input_returns_no_sessions():
    assert cr.partition_commit_sessions([], commit_gap_hours=4) == []


def test_single_commit_is_its_own_session():
    commits = _commits(("a", 0))

    sessions = cr.partition_commit_sessions(commits, commit_gap_hours=4)

    assert _shas(sessions) == [["a"]]


def test_accepts_dict_shaped_commits():
    commits = [
        {"sha": "a", "timestamp": _ts(0)},
        {"sha": "b", "timestamp": _ts(1)},
        {"sha": "c", "timestamp": _ts(6)},
    ]

    sessions = cr.partition_commit_sessions(commits, commit_gap_hours=4)

    assert _shas(sessions) == [["a", "b"], ["c"]]


def test_unsorted_input_is_partitioned_in_chronological_order():
    # git log emits newest-first; the partitioner re-sorts regardless of
    # the order it's handed.
    commits = _commits(("c", 6), ("a", 0), ("b", 1))

    sessions = cr.partition_commit_sessions(commits, commit_gap_hours=4)

    assert _shas(sessions) == [["a", "b"], ["c"]]


def test_default_commit_gap_hours_is_four():
    commits = _commits(("a", 0), ("b", 3.9), ("c", 8))

    sessions = cr.partition_commit_sessions(commits)

    assert _shas(sessions) == [["a", "b"], ["c"]]
