"""Tests for autoship_reclaim.py (#989)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

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
