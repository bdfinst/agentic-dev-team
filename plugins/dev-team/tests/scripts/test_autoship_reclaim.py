"""Tests for autoship_reclaim.py (#989)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import autoship_reclaim  # noqa: E402


def _issue(number: int, labeled_at: str, state: str = "OPEN", labels=None) -> dict:
    return {
        "number": number,
        "title": f"Issue {number}",
        "state": state,
        "labels": labels if labels is not None else [{"name": "autoship:in-progress"}],
        "labeled_at": labeled_at,
    }


# ---------------------------------------------------------------------------
# select_orphaned — pure staleness selector
# ---------------------------------------------------------------------------


def test_select_orphaned_reclaims_stale_issue() -> None:
    issues = [_issue(30, "2026-07-01T00:00:00Z")]
    now = datetime(2026, 7, 3, 0, 0, 0)
    result = autoship_reclaim.select_orphaned(issues, 24, now)
    assert [issue["number"] for issue in result] == [30]


def test_select_orphaned_inclusive_at_exact_threshold() -> None:
    issues = [_issue(32, "2026-07-01T00:00:00Z")]
    now = datetime(2026, 7, 2, 0, 0, 0)
    result = autoship_reclaim.select_orphaned(issues, 24, now)
    assert [issue["number"] for issue in result] == [32]


def test_select_orphaned_does_not_reclaim_fresh_issue() -> None:
    issues = [_issue(31, "2026-07-03T05:00:00Z")]
    now = datetime(2026, 7, 3, 6, 0, 0)
    result = autoship_reclaim.select_orphaned(issues, 24, now)
    assert result == []


def test_select_orphaned_multi_issue_mixed() -> None:
    issues = [
        _issue(40, "2026-07-01T00:00:00Z"),
        _issue(41, "2026-07-01T00:00:00Z"),
        _issue(42, "2026-07-03T05:00:00Z"),
    ]
    now = datetime(2026, 7, 3, 6, 0, 0)
    result = autoship_reclaim.select_orphaned(issues, 24, now)
    assert [issue["number"] for issue in result] == [40, 41]


def test_select_orphaned_empty_when_no_in_progress_issues() -> None:
    now = datetime(2026, 7, 3, 6, 0, 0)
    result = autoship_reclaim.select_orphaned([], 24, now)
    assert result == []


def test_select_orphaned_excludes_closed_issue() -> None:
    issues = [_issue(33, "2026-07-01T00:00:00Z", state="CLOSED")]
    now = datetime(2026, 7, 3, 0, 0, 0)
    result = autoship_reclaim.select_orphaned(issues, 24, now)
    assert result == []


def test_select_orphaned_excludes_issue_without_in_progress_label() -> None:
    issues = [_issue(34, "2026-07-01T00:00:00Z", labels=[{"name": "autoship:ready"}])]
    now = datetime(2026, 7, 3, 0, 0, 0)
    result = autoship_reclaim.select_orphaned(issues, 24, now)
    assert result == []


def test_select_orphaned_falls_back_to_updated_at() -> None:
    issue = {
        "number": 50,
        "title": "Issue 50",
        "state": "OPEN",
        "labels": [{"name": "autoship:in-progress"}],
        "updatedAt": "2026-07-01T00:00:00Z",
    }
    now = datetime(2026, 7, 3, 0, 0, 0)
    result = autoship_reclaim.select_orphaned([issue], 24, now)
    assert [issue["number"] for issue in result] == [50]


# ---------------------------------------------------------------------------
# CLI parser — --stale-after-hours default/validation, shared input seam
# ---------------------------------------------------------------------------


def test_stale_after_hours_defaults_to_24() -> None:
    parser = autoship_reclaim._build_parser()
    args = parser.parse_args([])
    assert args.stale_after_hours == 24


def test_stale_after_hours_rejects_zero() -> None:
    parser = autoship_reclaim._build_parser()
    try:
        parser.parse_args(["--stale-after-hours", "0"])
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code != 0


def test_stale_after_hours_rejects_negative() -> None:
    parser = autoship_reclaim._build_parser()
    try:
        parser.parse_args(["--stale-after-hours", "-1"])
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code != 0


def test_stale_after_hours_accepts_custom_value() -> None:
    parser = autoship_reclaim._build_parser()
    args = parser.parse_args(["--stale-after-hours", "48"])
    assert args.stale_after_hours == 48


def test_parser_has_shared_input_seam() -> None:
    parser = autoship_reclaim._build_parser()
    args = parser.parse_args(
        ["--input-file", "fixture.json", "--now-override", "2026-07-08T12:00:00Z"]
    )
    assert args.input_file == "fixture.json"
    assert args.now_override == datetime(2026, 7, 8, 12, 0, 0)


# ---------------------------------------------------------------------------
# Live gh fetch — issue list + per-issue timeline lookup
# ---------------------------------------------------------------------------


def _completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=0, stdout=stdout, stderr=""
    )


def test_fetch_in_progress_issues_raises_on_issue_list_failure() -> None:
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["gh", "issue", "list"]),
    ):
        try:
            autoship_reclaim._fetch_in_progress_issues()
            assert False, "expected CalledProcessError"
        except subprocess.CalledProcessError:
            pass


def test_fetch_in_progress_issues_uses_timeline_labeled_event() -> None:
    issue_list = _completed(
        json.dumps(
            [
                {
                    "number": 51,
                    "title": "Issue 51",
                    "state": "OPEN",
                    "labels": [{"name": "autoship:in-progress"}],
                    "updatedAt": "2026-07-05T00:00:00Z",
                }
            ]
        )
    )
    repo_view = _completed("OWNER/REPO")
    timeline = _completed(
        json.dumps(
            [
                {
                    "event": "labeled",
                    "label": {"name": "autoship:in-progress"},
                    "created_at": "2026-07-01T00:00:00Z",
                },
                {
                    "event": "labeled",
                    "label": {"name": "autoship:ready"},
                    "created_at": "2026-07-04T00:00:00Z",
                },
            ]
        )
    )
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[issue_list, repo_view, timeline],
    ):
        issues = autoship_reclaim._fetch_in_progress_issues()
    assert issues[0]["labeled_at"] == "2026-07-01T00:00:00Z"


def test_fetch_in_progress_issues_falls_back_when_timeline_fetch_fails() -> None:
    issue_list = _completed(
        json.dumps(
            [
                {
                    "number": 50,
                    "title": "Issue 50",
                    "state": "OPEN",
                    "labels": [{"name": "autoship:in-progress"}],
                    "updatedAt": "2026-07-05T00:00:00Z",
                }
            ]
        )
    )
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[
            issue_list,
            subprocess.CalledProcessError(1, ["gh", "repo", "view"]),
        ],
    ):
        issues = autoship_reclaim._fetch_in_progress_issues()
    assert issues[0]["labeled_at"] == "2026-07-05T00:00:00Z"


def test_fetch_in_progress_issues_falls_back_when_no_matching_labeled_event() -> None:
    issue_list = _completed(
        json.dumps(
            [
                {
                    "number": 52,
                    "title": "Issue 52",
                    "state": "OPEN",
                    "labels": [{"name": "autoship:in-progress"}],
                    "updatedAt": "2026-07-05T00:00:00Z",
                }
            ]
        )
    )
    repo_view = _completed("OWNER/REPO")
    timeline = _completed(json.dumps([{"event": "commented"}]))
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[issue_list, repo_view, timeline],
    ):
        issues = autoship_reclaim._fetch_in_progress_issues()
    assert issues[0]["labeled_at"] == "2026-07-05T00:00:00Z"


def test_mixed_timeline_success_and_failure_does_not_abort_run() -> None:
    """Covers 'Timeline lookup failure falls back to updatedAt' — #50's
    timeline fetch fails and falls back, #51's succeeds and uses the real
    labeled_at, and the run completes without error."""
    issue_list = _completed(
        json.dumps(
            [
                {
                    "number": 50,
                    "title": "Issue 50",
                    "state": "OPEN",
                    "labels": [{"name": "autoship:in-progress"}],
                    "updatedAt": "2026-07-05T00:00:00Z",
                },
                {
                    "number": 51,
                    "title": "Issue 51",
                    "state": "OPEN",
                    "labels": [{"name": "autoship:in-progress"}],
                    "updatedAt": "2026-07-06T00:00:00Z",
                },
            ]
        )
    )
    repo_view_1 = subprocess.CalledProcessError(1, ["gh", "repo", "view"])
    repo_view_2 = _completed("OWNER/REPO")
    timeline_2 = _completed(
        json.dumps(
            [
                {
                    "event": "labeled",
                    "label": {"name": "autoship:in-progress"},
                    "created_at": "2026-07-02T00:00:00Z",
                }
            ]
        )
    )
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[issue_list, repo_view_1, repo_view_2, timeline_2],
    ):
        issues = autoship_reclaim._fetch_in_progress_issues()
    assert issues[0]["labeled_at"] == "2026-07-05T00:00:00Z"  # fallback to updatedAt
    assert issues[1]["labeled_at"] == "2026-07-02T00:00:00Z"  # real timeline event


def test_input_file_and_live_fetch_converge_on_same_field_set(tmp_path) -> None:
    fixture = [
        {
            "number": 60,
            "title": "Issue 60",
            "state": "OPEN",
            "labels": [{"name": "autoship:in-progress"}],
            "labeled_at": "2026-07-01T00:00:00Z",
        }
    ]
    input_file = tmp_path / "issues.json"
    input_file.write_text(json.dumps(fixture))

    args = autoship_reclaim._build_parser().parse_args(
        ["--input-file", str(input_file)]
    )
    from_file = autoship_reclaim._load_issues(args)

    issue_list = _completed(json.dumps(fixture))
    repo_view = _completed("OWNER/REPO")
    timeline = _completed(
        json.dumps(
            [
                {
                    "event": "labeled",
                    "label": {"name": "autoship:in-progress"},
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ]
        )
    )
    live_args = autoship_reclaim._build_parser().parse_args([])
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[issue_list, repo_view, timeline],
    ):
        from_live = autoship_reclaim._load_issues(live_args)

    assert set(from_file[0].keys()) <= set(from_live[0].keys())
    for key in ("number", "title", "state", "labels", "labeled_at"):
        assert key in from_live[0]
        assert key in from_file[0]


def test_main_exits_nonzero_on_gh_fetch_failure(capsys) -> None:
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["gh", "issue", "list"]),
    ):
        rc = autoship_reclaim.main([])
    assert rc != 0
    captured = capsys.readouterr()
    assert "gh" in captured.err.lower()


def test_main_reports_no_op_when_no_in_progress_issues(tmp_path, capsys) -> None:
    input_file = tmp_path / "issues.json"
    input_file.write_text("[]")
    rc = autoship_reclaim.main(["--input-file", str(input_file)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "No orphaned" in captured.out


# ---------------------------------------------------------------------------
# --dry-run preview, live comment/relabel ordering, per-issue status output
# ---------------------------------------------------------------------------


def _stale_issue_file(tmp_path, number: int = 30) -> Path:
    fixture = [
        {
            "number": number,
            "title": f"Issue {number}",
            "state": "OPEN",
            "labels": [{"name": "autoship:in-progress"}],
            "labeled_at": "2026-07-01T00:00:00Z",
        }
    ]
    input_file = tmp_path / "issues.json"
    input_file.write_text(json.dumps(fixture))
    return input_file


def test_dry_run_makes_zero_gh_calls(tmp_path, capsys) -> None:
    input_file = _stale_issue_file(tmp_path, 30)
    with patch("autoship_reclaim.subprocess.run") as mock_run:
        rc = autoship_reclaim.main(
            [
                "--input-file",
                str(input_file),
                "--now-override",
                "2026-07-03T00:00:00Z",
                "--dry-run",
            ]
        )
    assert rc == 0
    assert mock_run.call_count == 0
    captured = capsys.readouterr()
    assert "would-reclaim #30" in captured.out
    assert "autoship:in-progress" in captured.out
    assert "autoship:blocked" in captured.out


def test_live_mode_comments_then_relabels_in_order(tmp_path, capsys) -> None:
    input_file = _stale_issue_file(tmp_path, 30)
    comment_result = subprocess.CompletedProcess(
        args=["gh"], returncode=0, stdout="", stderr=""
    )
    relabel_result = subprocess.CompletedProcess(
        args=["gh"], returncode=0, stdout="", stderr=""
    )
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[comment_result, relabel_result],
    ) as mock_run:
        rc = autoship_reclaim.main(
            [
                "--input-file",
                str(input_file),
                "--now-override",
                "2026-07-03T00:00:00Z",
            ]
        )
    assert rc == 0
    assert mock_run.call_count == 2

    comment_call = mock_run.call_args_list[0].args[0]
    relabel_call = mock_run.call_args_list[1].args[0]

    assert comment_call[:3] == ["gh", "issue", "comment"]
    assert "30" in comment_call
    assert relabel_call[:3] == ["gh", "issue", "edit"]
    assert "30" in relabel_call
    assert "--remove-label" in relabel_call
    assert "autoship:in-progress" in relabel_call
    assert "--add-label" in relabel_call
    assert "autoship:blocked" in relabel_call

    captured = capsys.readouterr()
    assert "reclaimed #30" in captured.out


def test_comment_failure_exits_nonzero_and_leaves_issue_retryable(
    tmp_path, capsys
) -> None:
    input_file = _stale_issue_file(tmp_path, 30)
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["gh", "issue", "comment"]),
    ) as mock_run:
        rc = autoship_reclaim.main(
            [
                "--input-file",
                str(input_file),
                "--now-override",
                "2026-07-03T00:00:00Z",
            ]
        )
    assert rc != 0
    assert mock_run.call_count == 1  # never reached relabel
    captured = capsys.readouterr()
    assert "#30" in captured.err
    assert "comment" in captured.err

    # A later run against the same (unchanged) fixture re-selects the issue.
    with open(input_file, encoding="utf-8") as fh:
        issues = json.load(fh)
    reselected = autoship_reclaim.select_orphaned(
        issues, 24, datetime(2026, 7, 3, 0, 0, 0)
    )
    assert [issue["number"] for issue in reselected] == [30]


def test_relabel_failure_after_successful_comment_exits_nonzero_and_retryable(
    tmp_path, capsys
) -> None:
    input_file = _stale_issue_file(tmp_path, 30)
    comment_result = subprocess.CompletedProcess(
        args=["gh"], returncode=0, stdout="", stderr=""
    )
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[
            comment_result,
            subprocess.CalledProcessError(1, ["gh", "issue", "edit"]),
        ],
    ) as mock_run:
        rc = autoship_reclaim.main(
            [
                "--input-file",
                str(input_file),
                "--now-override",
                "2026-07-03T00:00:00Z",
            ]
        )
    assert rc != 0
    assert mock_run.call_count == 2  # comment succeeded, relabel failed
    captured = capsys.readouterr()
    assert "#30" in captured.err
    assert "relabel" in captured.err

    # The fixture's label is unaffected by the failed relabel call (it's a
    # mock) — a later run against the same (still in-progress) issue
    # re-selects it, same as the comment-failure case.
    with open(input_file, encoding="utf-8") as fh:
        issues = json.load(fh)
    reselected = autoship_reclaim.select_orphaned(
        issues, 24, datetime(2026, 7, 3, 0, 0, 0)
    )
    assert [issue["number"] for issue in reselected] == [30]


def test_multi_issue_run_reports_one_status_line_per_issue(tmp_path, capsys) -> None:
    fixture = [
        {
            "number": 40,
            "title": "Issue 40",
            "state": "OPEN",
            "labels": [{"name": "autoship:in-progress"}],
            "labeled_at": "2026-07-01T00:00:00Z",
        },
        {
            "number": 41,
            "title": "Issue 41",
            "state": "OPEN",
            "labels": [{"name": "autoship:in-progress"}],
            "labeled_at": "2026-07-01T00:00:00Z",
        },
    ]
    input_file = tmp_path / "issues.json"
    input_file.write_text(json.dumps(fixture))

    ok = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="", stderr="")
    with patch("autoship_reclaim.subprocess.run", side_effect=[ok, ok, ok, ok]):
        rc = autoship_reclaim.main(
            [
                "--input-file",
                str(input_file),
                "--now-override",
                "2026-07-03T00:00:00Z",
            ]
        )
    assert rc == 0
    captured = capsys.readouterr()
    assert "reclaimed #40" in captured.out
    assert "reclaimed #41" in captured.out
