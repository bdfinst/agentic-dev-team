"""Tests for autoship_state.py (#989)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "lib"))

import autoship_state


def _issue(**overrides) -> dict:
    base = {
        "number": 1,
        "title": "Some issue",
        "state": "OPEN",
        "createdAt": "2026-07-01T00:00:00Z",
        "labels": [{"name": "autoship:ready"}],
        "closedByPullRequestsReferences": [],
        "subIssuesSummary": {"total": 0},
    }
    base.update(overrides)
    return base


def test_format_round_timestamp_returns_iso8601_z_suffixed() -> None:
    # Naive-UTC by design, matching autoship_state.py's own naive-UTC contract
    # (see its `_iso8601` noqa: DTZ007) — tzinfo would break comparisons below.
    dt = datetime(2026, 7, 8, 12, 0, 0)  # noqa: DTZ001
    assert autoship_state.format_round_timestamp(dt) == "2026-07-08T12:00:00Z"


def test_is_stale_true_when_elapsed_exceeds_threshold() -> None:
    labeled_at = datetime(2026, 7, 1, 0, 0, 0)  # noqa: DTZ001
    now = datetime(2026, 7, 3, 0, 0, 0)  # noqa: DTZ001
    assert autoship_state.is_stale(labeled_at, 24, now) is True


def test_is_stale_false_when_recently_labeled() -> None:
    labeled_at = datetime(2026, 7, 3, 5, 0, 0)  # noqa: DTZ001
    now = datetime(2026, 7, 3, 6, 0, 0)  # noqa: DTZ001
    assert autoship_state.is_stale(labeled_at, 24, now) is False


def test_is_stale_inclusive_at_exact_threshold() -> None:
    labeled_at = datetime(2026, 7, 1, 0, 0, 0)  # noqa: DTZ001
    now = datetime(2026, 7, 2, 0, 0, 0)  # noqa: DTZ001
    assert autoship_state.is_stale(labeled_at, 24, now) is True


def test_add_input_seam_args_accepts_both_flags() -> None:
    parser = argparse.ArgumentParser()
    autoship_state.add_input_seam_args(parser)
    args = parser.parse_args(
        ["--input-file", "fixture.json", "--now-override", "2026-07-08T12:00:00Z"]
    )
    assert args.input_file == "fixture.json"
    assert args.now_override == datetime(2026, 7, 8, 12, 0, 0)  # noqa: DTZ001


def test_add_input_seam_args_both_flags_optional() -> None:
    parser = argparse.ArgumentParser()
    autoship_state.add_input_seam_args(parser)
    args = parser.parse_args([])
    assert args.input_file is None
    assert args.now_override is None


# ---------------------------------------------------------------------------
# positive_int_validator
# ---------------------------------------------------------------------------


def test_positive_int_validator_accepts_positive_value() -> None:
    validator = autoship_state.positive_int_validator("--max-issues")
    assert validator("3") == 3


def test_positive_int_validator_rejects_zero() -> None:
    validator = autoship_state.positive_int_validator("--max-issues")
    with pytest.raises(argparse.ArgumentTypeError):
        validator("0")


def test_positive_int_validator_rejects_negative() -> None:
    validator = autoship_state.positive_int_validator("--max-issues")
    with pytest.raises(argparse.ArgumentTypeError):
        validator("-1")


# ---------------------------------------------------------------------------
# fetch_eligible_issues / FetchError
# ---------------------------------------------------------------------------


def test_fetch_eligible_issues_from_input_file_filters_and_sorts_oldest_first(
    tmp_path,
) -> None:
    older = _issue(number=1, createdAt="2026-07-01T00:00:00Z")
    newer = _issue(number=2, createdAt="2026-07-02T00:00:00Z")
    ineligible = _issue(number=3, state="CLOSED")
    fixture = tmp_path / "issues.json"
    fixture.write_text(json.dumps([newer, older, ineligible]), encoding="utf-8")

    result = autoship_state.fetch_eligible_issues(
        "autoship:ready", input_file=str(fixture)
    )

    assert [issue["number"] for issue in result] == [1, 2]


def test_fetch_eligible_issues_gh_not_found_raises_fetch_error(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise FileNotFoundError("gh not on PATH")

    monkeypatch.setattr(subprocess, "run", _raise)

    with pytest.raises(autoship_state.FetchError):
        autoship_state.fetch_eligible_issues("autoship:ready")


def test_fetch_eligible_issues_malformed_input_file_raises_fetch_error(
    tmp_path,
) -> None:
    bad_issue = _issue()
    del bad_issue["state"]
    fixture = tmp_path / "issues.json"
    fixture.write_text(json.dumps([bad_issue]), encoding="utf-8")

    with pytest.raises(autoship_state.FetchError):
        autoship_state.fetch_eligible_issues("autoship:ready", input_file=str(fixture))
