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
# is_eligible — direct unit tests (ported from autoship_discover.py's
# select_eligible tests when select_eligible was deleted as dead code
# (#2075): is_eligible's exclusion rules had no coverage of their own before
# this — select_eligible's tests exercised them only indirectly)
# ---------------------------------------------------------------------------


def test_is_eligible_true_for_well_formed_issue() -> None:
    assert autoship_state.is_eligible(_issue(), "autoship:ready") is True


def test_is_eligible_excludes_epic() -> None:
    epic = _issue(subIssuesSummary={"total": 2})
    assert autoship_state.is_eligible(epic, "autoship:ready") is False


def test_is_eligible_excludes_in_progress() -> None:
    issue = _issue(
        labels=[{"name": "autoship:ready"}, {"name": "autoship:in-progress"}]
    )
    assert autoship_state.is_eligible(issue, "autoship:ready") is False


def test_is_eligible_excludes_blocked() -> None:
    issue = _issue(labels=[{"name": "autoship:ready"}, {"name": "autoship:blocked"}])
    assert autoship_state.is_eligible(issue, "autoship:ready") is False


def test_is_eligible_excludes_open_linked_pr() -> None:
    issue = _issue(closedByPullRequestsReferences=[{"number": 99, "state": "OPEN"}])
    assert autoship_state.is_eligible(issue, "autoship:ready") is False


def test_is_eligible_includes_merged_only_pr() -> None:
    issue = _issue(closedByPullRequestsReferences=[{"number": 99, "state": "MERGED"}])
    assert autoship_state.is_eligible(issue, "autoship:ready") is True


def test_is_eligible_includes_closed_not_merged_pr() -> None:
    issue = _issue(closedByPullRequestsReferences=[{"number": 99, "state": "CLOSED"}])
    assert autoship_state.is_eligible(issue, "autoship:ready") is True


def test_is_eligible_excludes_mixed_open_and_closed_pr() -> None:
    issue = _issue(
        closedByPullRequestsReferences=[
            {"number": 98, "state": "MERGED"},
            {"number": 99, "state": "OPEN"},
        ]
    )
    assert autoship_state.is_eligible(issue, "autoship:ready") is False


def test_is_eligible_excludes_closed_issue() -> None:
    issue = _issue(state="CLOSED")
    assert autoship_state.is_eligible(issue, "autoship:ready") is False


def test_is_eligible_custom_label_overrides_default() -> None:
    ready_only = _issue(number=20, labels=[{"name": "autoship:ready"}])
    custom_labeled = _issue(number=21, labels=[{"name": "custom-label"}])
    assert autoship_state.is_eligible(ready_only, "custom-label") is False
    assert autoship_state.is_eligible(custom_labeled, "custom-label") is True


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


def test_fetch_issues_from_gh_passes_limit_500(monkeypatch) -> None:
    # `gh issue list` applies a default result cap (typically 30);
    # fetch_issues_from_gh is documented as returning the FULL eligible
    # pool, which is only true with an explicit --limit override.
    captured_argv = {}

    def _fake_run(argv, **kwargs):
        captured_argv["argv"] = argv
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    autoship_state.fetch_issues_from_gh("autoship:ready")

    argv = captured_argv["argv"]
    assert "--limit" in argv
    assert argv[argv.index("--limit") + 1] == "500"


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


# ---------------------------------------------------------------------------
# validate_issues — shape validation (#2074)
# ---------------------------------------------------------------------------


def test_validate_issues_accepts_well_shaped_issue() -> None:
    autoship_state.validate_issues([_issue()])  # no raise


def test_validate_issues_rejects_labels_as_bare_strings() -> None:
    issue = _issue(labels=["autoship:ready"])
    with pytest.raises(autoship_state.FetchError, match="labels"):
        autoship_state.validate_issues([issue])


def test_validate_issues_rejects_labels_not_a_list() -> None:
    issue = _issue(labels={"name": "autoship:ready"})
    with pytest.raises(autoship_state.FetchError, match="labels"):
        autoship_state.validate_issues([issue])


def test_validate_issues_rejects_label_entry_missing_name() -> None:
    issue = _issue(labels=[{"color": "green"}])
    with pytest.raises(autoship_state.FetchError, match="labels"):
        autoship_state.validate_issues([issue])


def test_validate_issues_rejects_sub_issues_summary_not_an_object() -> None:
    issue = _issue(subIssuesSummary=2)
    with pytest.raises(autoship_state.FetchError, match="subIssuesSummary"):
        autoship_state.validate_issues([issue])


def test_validate_issues_rejects_sub_issues_summary_total_not_numeric() -> None:
    issue = _issue(subIssuesSummary={"total": "zero"})
    with pytest.raises(autoship_state.FetchError, match="subIssuesSummary"):
        autoship_state.validate_issues([issue])


def test_validate_issues_rejects_closed_by_pull_requests_references_not_a_list() -> (
    None
):
    issue = _issue(closedByPullRequestsReferences={"state": "OPEN"})
    with pytest.raises(
        autoship_state.FetchError, match="closedByPullRequestsReferences"
    ):
        autoship_state.validate_issues([issue])


def test_validate_issues_rejects_closed_by_pull_requests_references_entry_not_object() -> (
    None
):
    issue = _issue(closedByPullRequestsReferences=["OPEN"])
    with pytest.raises(
        autoship_state.FetchError, match="closedByPullRequestsReferences"
    ):
        autoship_state.validate_issues([issue])


def test_validate_issues_shape_error_names_the_issue_number() -> None:
    issue = _issue(number=77, labels=["autoship:ready"])
    with pytest.raises(autoship_state.FetchError, match="#77"):
        autoship_state.validate_issues([issue])


def test_fetch_eligible_issues_malformed_label_shape_raises_fetch_error(
    tmp_path,
) -> None:
    bad_issue = _issue(labels=["autoship:ready"])
    fixture = tmp_path / "issues.json"
    fixture.write_text(json.dumps([bad_issue]), encoding="utf-8")

    with pytest.raises(autoship_state.FetchError):
        autoship_state.fetch_eligible_issues("autoship:ready", input_file=str(fixture))
