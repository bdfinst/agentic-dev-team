"""Unit tests for scripts/lib/churn_recurrence.py (issue #2039, Steps 2.2b/2.3).

Pins the commit-gap session-boundary heuristic: `partition_commit_sessions`
groups a file's commits into `commit_session` groups by timestamp gap, with
an inclusive boundary (a gap exactly equal to `commit_gap_hours` starts a
new commit-session -- matching `churn_coupling_report.py`'s existing
`--max-commits` inclusive-boundary convention). Also pins `rank_all_files`
(Step 2.3): every historically-edited path ranked by cross-session
recurrence, with an `unattributed` section distinct from the existing
mode's `unmapped` key.
"""

from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# rank_all_files (Step 2.3, #2039)
# ---------------------------------------------------------------------------


def _all_files_commits(*specs):
    """Build `(sha, paths, timestamp)` tuples from `(sha, [paths], hours)`."""
    return [(sha, paths, _ts(hours)) for sha, paths, hours in specs]


def _row_by_path(report, path):
    for row in report["rows"]:
        if row.path == path:
            return row
    raise AssertionError(f"{path} not in ranked rows: {[r.path for r in report['rows']]}")


class TestRankAllFiles:
    def test_ranks_files_by_cross_session_count_descending(self):
        # src/alpha.py: two commit-sessions (10h apart) -> cross_session=1.
        # tests/test_beta.py: one commit-session (1h apart) -> cross_session=0.
        commits = _all_files_commits(
            ("a", ["src/alpha.py"], 0),
            ("b", ["src/alpha.py"], 10),
            ("c", ["tests/test_beta.py"], 0),
            ("d", ["tests/test_beta.py"], 1),
        )
        tracked = {"src/alpha.py", "tests/test_beta.py"}

        report = cr.rank_all_files(commits, tracked, commit_gap_hours=4)

        assert [row.path for row in report["rows"]] == ["src/alpha.py", "tests/test_beta.py"]
        alpha = _row_by_path(report, "src/alpha.py")
        assert (alpha.edits, alpha.within_session, alpha.cross_session) == (2, 1, 1)
        beta = _row_by_path(report, "tests/test_beta.py")
        assert (beta.edits, beta.within_session, beta.cross_session) == (2, 2, 0)

    def test_within_commit_session_edits_score_zero_cross_session(self):
        """A file edited only within a single commit-session never recurs."""
        commits = _all_files_commits(
            ("a", ["src/alpha.py"], 0),
            ("b", ["src/alpha.py"], 1),
            ("c", ["src/alpha.py"], 2),
        )
        report = cr.rank_all_files(commits, {"src/alpha.py"}, commit_gap_hours=4)

        row = _row_by_path(report, "src/alpha.py")
        assert (row.edits, row.within_session, row.cross_session) == (3, 3, 0)

    def test_gap_exactly_at_threshold_counts_as_cross_session(self):
        commits = _all_files_commits(
            ("a", ["src/alpha.py"], 0),
            ("b", ["src/alpha.py"], 4),
        )
        report = cr.rank_all_files(commits, {"src/alpha.py"}, commit_gap_hours=4)

        row = _row_by_path(report, "src/alpha.py")
        assert row.cross_session == 1

    def test_ties_are_broken_by_edits_then_path(self):
        commits = _all_files_commits(
            ("a", ["b/beta.py"], 0),
            ("b", ["b/beta.py"], 10),
            ("c", ["a/alpha.py"], 0),
            ("d", ["a/alpha.py"], 10),
        )
        report = cr.rank_all_files(
            commits, {"a/alpha.py", "b/beta.py"}, commit_gap_hours=4
        )

        assert [row.path for row in report["rows"]] == ["a/alpha.py", "b/beta.py"]

    def test_unattributable_file_is_reported_as_unattributed_not_unmapped_or_ranked(self):
        """A file with no clean path back to a current working-tree file (here:
        simply untracked) is reported in `unattributed`, never `unmapped`
        (the existing mode's distinct key -- see the module docstring), and
        never appears in the ranked `rows`.
        """
        commits = _all_files_commits(
            ("a", ["src/gone.py"], 0),
            ("b", ["src/gone.py"], 10),
        )
        report = cr.rank_all_files(commits, tracked=set(), commit_gap_hours=4)

        assert report["rows"] == []
        assert [u["path"] for u in report["unattributed"]] == ["src/gone.py"]
        assert report["unattributed"][0]["edits"] == 2
        assert "unmapped" not in report

    def test_unattributed_file_is_never_scored_zero_in_rows(self):
        commits = _all_files_commits(("a", ["src/gone.py"], 0))
        report = cr.rank_all_files(commits, tracked=set(), commit_gap_hours=4)

        assert all(row.path != "src/gone.py" for row in report["rows"])

    def test_accepts_dict_shaped_commits(self):
        commits = [
            {"sha": "a", "paths": ["src/alpha.py"], "timestamp": _ts(0)},
            {"sha": "b", "paths": ["src/alpha.py"], "timestamp": _ts(10)},
        ]
        report = cr.rank_all_files(commits, {"src/alpha.py"}, commit_gap_hours=4)

        row = _row_by_path(report, "src/alpha.py")
        assert row.cross_session == 1

    def test_files_seen_counts_ranked_and_unattributed_together(self):
        commits = _all_files_commits(
            ("a", ["src/alpha.py"], 0),
            ("b", ["src/gone.py"], 0),
        )
        report = cr.rank_all_files(commits, {"src/alpha.py"}, commit_gap_hours=4)

        assert report["files_seen"] == 2
        assert report["commits_scanned"] == 2

    def test_a_commit_touching_multiple_paths_is_counted_once_per_path(self):
        commits = _all_files_commits(
            ("a", ["src/alpha.py", "tests/test_alpha.py"], 0),
        )
        report = cr.rank_all_files(
            commits, {"src/alpha.py", "tests/test_alpha.py"}, commit_gap_hours=4
        )

        assert _row_by_path(report, "src/alpha.py").edits == 1
        assert _row_by_path(report, "tests/test_alpha.py").edits == 1


class TestRenderAllFiles:
    def _report(self, **overrides):
        commits = _all_files_commits(
            ("a", ["src/alpha.py"], 0),
            ("b", ["src/alpha.py"], 10),
            ("c", ["src/gone.py"], 0),
        )
        report = cr.rank_all_files(commits, {"src/alpha.py"}, commit_gap_hours=4)
        report.setdefault("window", "90 days")
        report.setdefault("truncated", False)
        report.update(overrides)
        return report

    def test_render_text_shows_the_ranked_row_and_the_unattributed_section(self):
        text = cr.render_text(self._report(), top=10)
        assert "src/alpha.py" in text
        assert "Unattributed" in text
        assert "src/gone.py" in text

    def test_render_text_unattributed_header_is_distinct_from_unmapped(self):
        text = cr.render_text(self._report(), top=10)
        assert "Unmapped" not in text

    def test_render_json_row_shape(self):
        payload = json.loads(cr.render_json(self._report(), top=10))
        assert payload["rows"][0] == {
            "rank": 1,
            "path": "src/alpha.py",
            "edits": 2,
            "within_session": 1,
            "cross_session": 1,
        }
        assert payload["unattributed"] == [{"path": "src/gone.py", "edits": 1}]
