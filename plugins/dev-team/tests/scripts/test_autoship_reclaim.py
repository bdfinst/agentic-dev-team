"""Tests for autoship_reclaim.py (#989)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

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
    # --paginate --slurp wraps pages in an outer array; one page here.
    timeline = _completed(
        json.dumps(
            [
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
            ]
        )
    )
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[issue_list, repo_view, timeline],
    ):
        issues = autoship_reclaim._fetch_in_progress_issues()
    assert issues[0]["labeled_at"] == "2026-07-01T00:00:00Z"


def test_fetch_in_progress_issues_falls_back_when_repo_resolution_fails() -> None:
    """Repo resolution is a single once-per-run call (#989 code review
    finding: it previously ran once per issue); if it fails, every issue
    falls back to updatedAt rather than aborting the run."""
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


def test_fetch_in_progress_issues_repo_resolved_once_for_multiple_issues() -> None:
    """Repo resolution happens exactly once per run, not once per issue."""
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
    repo_view = _completed("OWNER/REPO")
    timeline_empty = _completed(json.dumps([]))
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[issue_list, repo_view, timeline_empty, timeline_empty],
    ) as mock_run:
        autoship_reclaim._fetch_in_progress_issues()
    # 1 issue-list call + 1 repo-view call + 2 timeline calls (one per
    # issue) = 4 total, not 5 (which would mean repo view ran per-issue).
    assert mock_run.call_count == 4


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
    timeline = _completed(json.dumps([[{"event": "commented"}]]))
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[issue_list, repo_view, timeline],
    ):
        issues = autoship_reclaim._fetch_in_progress_issues()
    assert issues[0]["labeled_at"] == "2026-07-05T00:00:00Z"


def test_fetch_timeline_flattens_multiple_pages() -> None:
    """--paginate --slurp returns one JSON array per page (an array of
    arrays); _fetch_timeline must flatten them so a busy issue's
    most-recent labeled event (which may live on a later page) is still
    found (#989 code review finding: an unpaginated fetch could silently
    return only the first page)."""
    two_pages = _completed(
        json.dumps(
            [
                [{"event": "commented"}],  # page 1
                [
                    {
                        "event": "labeled",
                        "label": {"name": "autoship:in-progress"},
                        "created_at": "2026-07-01T00:00:00Z",
                    }
                ],  # page 2
            ]
        )
    )
    with patch("autoship_reclaim.subprocess.run", return_value=two_pages) as mock_run:
        events = autoship_reclaim._fetch_timeline(60, "OWNER/REPO")
    assert events == [
        {"event": "commented"},
        {
            "event": "labeled",
            "label": {"name": "autoship:in-progress"},
            "created_at": "2026-07-01T00:00:00Z",
        },
    ]
    assert "--paginate" in mock_run.call_args[0][0]
    assert "--slurp" in mock_run.call_args[0][0]


def test_mixed_timeline_success_and_failure_does_not_abort_run() -> None:
    """Covers 'Timeline lookup failure falls back to updatedAt' — #50's
    per-issue timeline fetch fails and falls back, #51's succeeds and uses
    the real labeled_at, and the run completes without error. Repo
    resolution itself succeeds once and is shared by both issues (#989
    code review finding: resolving it per-issue cost one redundant
    `gh repo view` call per orphan candidate)."""
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
    repo_view = _completed("OWNER/REPO")
    timeline_50 = subprocess.CalledProcessError(1, ["gh", "api"])
    timeline_51 = _completed(
        json.dumps(
            [
                [
                    {
                        "event": "labeled",
                        "label": {"name": "autoship:in-progress"},
                        "created_at": "2026-07-02T00:00:00Z",
                    }
                ]
            ]
        )
    )
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[issue_list, repo_view, timeline_50, timeline_51],
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
                [
                    {
                        "event": "labeled",
                        "label": {"name": "autoship:in-progress"},
                        "created_at": "2026-07-01T00:00:00Z",
                    }
                ]
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


def test_multi_issue_run_continues_after_one_issue_fails(tmp_path, capsys) -> None:
    """A failure on one issue must not abort the batch (#989 code review finding):
    every orphaned issue is attempted, not just those before the first failure."""
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
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[
            subprocess.CalledProcessError(
                1, ["gh", "issue", "comment"]
            ),  # #40 comment fails
            ok,  # #41 comment succeeds
            ok,  # #41 relabel succeeds
        ],
    ):
        rc = autoship_reclaim.main(
            [
                "--input-file",
                str(input_file),
                "--now-override",
                "2026-07-03T00:00:00Z",
            ]
        )
    assert rc != 0
    captured = capsys.readouterr()
    assert "#40" in captured.err
    assert "comment" in captured.err
    assert "reclaimed #41" in captured.out


# ---------------------------------------------------------------------------
# validate_issues / --input-file schema validation (#989 code review finding:
# reclaim previously had no equivalent to autoship_discover's validate_issues,
# risking an uncaught AttributeError on malformed local input)
# ---------------------------------------------------------------------------


def test_validate_issues_rejects_non_list() -> None:
    with pytest.raises(autoship_reclaim.ReclaimError, match="JSON array"):
        autoship_reclaim.validate_issues({"not": "a list"})


def test_validate_issues_rejects_non_dict_entry() -> None:
    with pytest.raises(autoship_reclaim.ReclaimError, match="not a JSON object"):
        autoship_reclaim.validate_issues([1, 2, 3])


def test_validate_issues_rejects_missing_field() -> None:
    with pytest.raises(autoship_reclaim.ReclaimError, match="missing required"):
        autoship_reclaim.validate_issues([{"number": 1, "title": "x"}])


def test_main_exits_nonzero_on_malformed_input_file(tmp_path, capsys) -> None:
    input_file = tmp_path / "bad.json"
    input_file.write_text(json.dumps([{"number": 1}]))
    rc = autoship_reclaim.main(["--input-file", str(input_file)])
    assert rc != 0
    captured = capsys.readouterr()
    assert "missing required" in captured.err
    assert "Traceback" not in captured.err


def test_main_exits_nonzero_on_non_list_input_file(tmp_path, capsys) -> None:
    input_file = tmp_path / "bad.json"
    input_file.write_text(json.dumps({"number": 1}))
    rc = autoship_reclaim.main(["--input-file", str(input_file)])
    assert rc != 0
    captured = capsys.readouterr()
    assert "JSON array" in captured.err
    assert "Traceback" not in captured.err


# ---------------------------------------------------------------------------
# gh subprocess timeouts (#989 code review finding: missing timeout= on
# every gh subprocess.run call risked an indefinite hang)
# ---------------------------------------------------------------------------


def test_fetch_in_progress_issues_passes_timeout() -> None:
    issue_list = _completed(json.dumps([]))
    with patch("autoship_reclaim.subprocess.run", return_value=issue_list) as mock_run:
        autoship_reclaim._fetch_in_progress_issues()
    assert mock_run.call_args_list[0].kwargs["timeout"] == (
        autoship_reclaim._GH_TIMEOUT_SECONDS
    )


def test_post_comment_and_relabel_pass_timeout() -> None:
    ok = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="", stderr="")
    with patch("autoship_reclaim.subprocess.run", return_value=ok) as mock_run:
        autoship_reclaim._post_comment(1, "body")
        autoship_reclaim._relabel(1)
    for call in mock_run.call_args_list:
        assert call.kwargs["timeout"] == autoship_reclaim._GH_TIMEOUT_SECONDS


def test_load_issues_timeout_surfaces_as_clear_stderr(capsys) -> None:
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["gh"], timeout=30),
    ):
        rc = autoship_reclaim.main([])
    assert rc != 0
    captured = capsys.readouterr()
    assert "failed to fetch in-progress issues via gh" in captured.err


# ---------------------------------------------------------------------------
# Missing gh binary (#989 /pr-gate finding: FileNotFoundError from a missing
# gh CLI was uncaught in reclaim's comment/relabel/fetch paths, unlike
# discovery's matching guard — surfaced a raw traceback instead of a clear
# stderr message, violating Acceptance Criterion 5)
# ---------------------------------------------------------------------------


def test_main_exits_nonzero_when_gh_binary_missing(capsys) -> None:
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=FileNotFoundError("gh: command not found"),
    ):
        rc = autoship_reclaim.main([])
    assert rc != 0
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "gh" in captured.err.lower()


def test_reclaim_issue_comment_missing_gh_binary_surfaces_clearly(capsys) -> None:
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=FileNotFoundError("gh: command not found"),
    ):
        rc = autoship_reclaim._reclaim_issue(
            _issue(30, "2026-07-01T00:00:00Z"), 24, datetime(2026, 7, 3, 0, 0, 0), False
        )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "#30" in captured.err


def test_labeled_at_for_falls_back_when_gh_binary_missing() -> None:
    issue = {"number": 55, "updatedAt": "2026-07-05T00:00:00Z"}
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=FileNotFoundError("gh: command not found"),
    ):
        labeled_at = autoship_reclaim._labeled_at_for(issue, "OWNER/REPO")
    assert labeled_at == "2026-07-05T00:00:00Z"


def test_load_issues_distinguishes_input_file_error_from_gh_error(
    tmp_path, capsys
) -> None:
    """A --input-file failure must not be blamed on gh (#989 /pr-gate
    finding: main()'s catch-all previously said 'Failed to load
    in-progress issues via gh' even for local file errors)."""
    input_file = tmp_path / "missing.json"  # never created
    rc = autoship_reclaim.main(["--input-file", str(input_file)])
    assert rc != 0
    captured = capsys.readouterr()
    assert "--input-file" in captured.err
    assert "gh" not in captured.err.lower().split("--input-file")[0]
