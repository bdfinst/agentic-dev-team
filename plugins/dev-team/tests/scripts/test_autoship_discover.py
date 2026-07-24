"""Tests for autoship_discover.py (#989)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import autoship_discover


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


# ---------------------------------------------------------------------------
# Step 2.1 — CLI boundary: required --max-issues/--max-cost-usd, --label default
# ---------------------------------------------------------------------------


def test_max_issues_and_max_cost_usd_both_required() -> None:
    with pytest.raises(SystemExit):
        autoship_discover.build_parser().parse_args([])


def test_missing_max_issues_only_is_a_hard_failure() -> None:
    with pytest.raises(SystemExit):
        autoship_discover.build_parser().parse_args(["--max-cost-usd", "10"])


def test_missing_max_cost_usd_only_is_a_hard_failure() -> None:
    with pytest.raises(SystemExit):
        autoship_discover.build_parser().parse_args(["--max-issues", "3"])


def test_both_present_parses_successfully() -> None:
    args = autoship_discover.build_parser().parse_args(
        ["--max-issues", "3", "--max-cost-usd", "10"]
    )
    assert args.max_issues == 3
    assert args.max_cost_usd == 10.0


def test_label_defaults_to_autoship_ready() -> None:
    args = autoship_discover.build_parser().parse_args(
        ["--max-issues", "3", "--max-cost-usd", "10"]
    )
    assert args.label == "autoship:ready"


def test_label_override() -> None:
    args = autoship_discover.build_parser().parse_args(
        ["--max-issues", "3", "--max-cost-usd", "10", "--label", "custom-label"]
    )
    assert args.label == "custom-label"


def test_max_issues_rejects_zero() -> None:
    with pytest.raises(SystemExit):
        autoship_discover.build_parser().parse_args(
            ["--max-issues", "0", "--max-cost-usd", "10"]
        )


def test_max_issues_rejects_negative() -> None:
    with pytest.raises(SystemExit):
        autoship_discover.build_parser().parse_args(
            ["--max-issues", "-1", "--max-cost-usd", "10"]
        )


def test_max_cost_usd_rejects_zero() -> None:
    with pytest.raises(SystemExit):
        autoship_discover.build_parser().parse_args(
            ["--max-issues", "3", "--max-cost-usd", "0"]
        )


def test_max_cost_usd_rejects_negative() -> None:
    with pytest.raises(SystemExit):
        autoship_discover.build_parser().parse_args(
            ["--max-issues", "3", "--max-cost-usd", "-1.5"]
        )


def test_shared_input_seam_flags_present() -> None:
    args = autoship_discover.build_parser().parse_args(
        [
            "--max-issues",
            "3",
            "--max-cost-usd",
            "10",
            "--input-file",
            "fixture.json",
            "--now-override",
            "2026-07-08T12:00:00Z",
        ]
    )
    assert args.input_file == "fixture.json"
    assert args.now_override is not None


def test_input_file_bypasses_gh_invocation(tmp_path, monkeypatch) -> None:
    """A smoke test that --input-file never shells out to `gh`."""

    def _raise(*args, **kwargs):
        raise AssertionError(
            "subprocess.run must not be called when --input-file is given"
        )

    monkeypatch.setattr(subprocess, "run", _raise)

    fixture = tmp_path / "issues.json"
    fixture.write_text(json.dumps([_issue()]), encoding="utf-8")

    exit_code = autoship_discover.main(
        ["--max-issues", "3", "--max-cost-usd", "10", "--input-file", str(fixture)]
    )
    assert exit_code == 0


def test_malformed_input_file_missing_field_exits_nonzero(tmp_path, capsys) -> None:
    fixture = tmp_path / "issues.json"
    bad_issue = _issue()
    del bad_issue["state"]
    fixture.write_text(json.dumps([bad_issue]), encoding="utf-8")

    exit_code = autoship_discover.main(
        ["--max-issues", "3", "--max-cost-usd", "10", "--input-file", str(fixture)]
    )
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "state" in captured.err
    assert "#1" in captured.err


def test_malformed_input_file_not_a_list_exits_nonzero(tmp_path) -> None:
    fixture = tmp_path / "issues.json"
    fixture.write_text(json.dumps({"not": "a list"}), encoding="utf-8")

    exit_code = autoship_discover.main(
        ["--max-issues", "3", "--max-cost-usd", "10", "--input-file", str(fixture)]
    )
    assert exit_code != 0


def test_malformed_input_file_invalid_json_exits_nonzero(tmp_path) -> None:
    fixture = tmp_path / "issues.json"
    fixture.write_text("{not valid json", encoding="utf-8")

    exit_code = autoship_discover.main(
        ["--max-issues", "3", "--max-cost-usd", "10", "--input-file", str(fixture)]
    )
    assert exit_code != 0


# ---------------------------------------------------------------------------
# Step 2.2 — pure eligibility filter, oldest-first cap, stdout contract
# ---------------------------------------------------------------------------


def test_select_eligible_oldest_first_capped_at_max_issues() -> None:
    issue_10 = _issue(number=10, createdAt="2026-07-01T00:00:00Z")
    issue_11 = _issue(number=11, createdAt="2026-07-02T00:00:00Z")
    selected = autoship_discover.select_eligible(
        [issue_11, issue_10], "autoship:ready", 1
    )
    assert [i["number"] for i in selected] == [10]


def test_select_eligible_count_exactly_matches_cap() -> None:
    issues = [_issue(number=n, createdAt=f"2026-07-0{n}T00:00:00Z") for n in (1, 2, 3)]
    selected = autoship_discover.select_eligible(issues, "autoship:ready", 3)
    assert [i["number"] for i in selected] == [1, 2, 3]


def test_select_eligible_max_issues_zero_selects_nothing() -> None:
    issues = [_issue(number=n, createdAt=f"2026-07-0{n}T00:00:00Z") for n in (1, 2, 3)]
    selected = autoship_discover.select_eligible(issues, "autoship:ready", 0)
    assert selected == []


def test_select_eligible_excludes_epic() -> None:
    epic = _issue(subIssuesSummary={"total": 2})
    assert autoship_discover.select_eligible([epic], "autoship:ready", 5) == []


def test_select_eligible_excludes_in_progress() -> None:
    issue = _issue(
        labels=[{"name": "autoship:ready"}, {"name": "autoship:in-progress"}]
    )
    assert autoship_discover.select_eligible([issue], "autoship:ready", 5) == []


def test_select_eligible_excludes_blocked() -> None:
    issue = _issue(labels=[{"name": "autoship:ready"}, {"name": "autoship:blocked"}])
    assert autoship_discover.select_eligible([issue], "autoship:ready", 5) == []


def test_select_eligible_excludes_open_linked_pr() -> None:
    issue = _issue(closedByPullRequestsReferences=[{"number": 99, "state": "OPEN"}])
    assert autoship_discover.select_eligible([issue], "autoship:ready", 5) == []


def test_select_eligible_includes_merged_only_pr() -> None:
    issue = _issue(closedByPullRequestsReferences=[{"number": 99, "state": "MERGED"}])
    selected = autoship_discover.select_eligible([issue], "autoship:ready", 5)
    assert [i["number"] for i in selected] == [1]


def test_select_eligible_includes_closed_not_merged_pr() -> None:
    issue = _issue(closedByPullRequestsReferences=[{"number": 99, "state": "CLOSED"}])
    selected = autoship_discover.select_eligible([issue], "autoship:ready", 5)
    assert [i["number"] for i in selected] == [1]


def test_select_eligible_excludes_mixed_open_and_closed_pr() -> None:
    issue = _issue(
        closedByPullRequestsReferences=[
            {"number": 98, "state": "MERGED"},
            {"number": 99, "state": "OPEN"},
        ]
    )
    assert autoship_discover.select_eligible([issue], "autoship:ready", 5) == []


def test_select_eligible_excludes_closed_issue() -> None:
    issue = _issue(state="CLOSED")
    assert autoship_discover.select_eligible([issue], "autoship:ready", 5) == []


def test_select_eligible_custom_label_overrides_default() -> None:
    issue_20 = _issue(number=20, labels=[{"name": "autoship:ready"}])
    issue_21 = _issue(number=21, labels=[{"name": "custom-label"}])
    selected = autoship_discover.select_eligible(
        [issue_20, issue_21], "custom-label", 5
    )
    assert [i["number"] for i in selected] == [21]


def test_select_eligible_empty_result_when_none_qualify() -> None:
    assert autoship_discover.select_eligible([], "autoship:ready", 5) == []


def test_select_eligible_stdout_shape_on_successful_run(tmp_path, capsys) -> None:
    fixture = tmp_path / "issues.json"
    fixture.write_text(
        json.dumps([_issue(number=42, title="Fix the thing")]), encoding="utf-8"
    )

    exit_code = autoship_discover.main(
        ["--max-issues", "5", "--max-cost-usd", "10", "--input-file", str(fixture)]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == [{"number": 42, "title": "Fix the thing"}]


# ---------------------------------------------------------------------------
# Step 2.3 — live gh fetch wiring and failure surfacing
# ---------------------------------------------------------------------------


def test_gh_fetch_failure_exits_nonzero_with_clear_stderr(monkeypatch, capsys) -> None:
    def _fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1, cmd=["gh", "issue", "list"], stderr="rate limited"
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    exit_code = autoship_discover.main(["--max-issues", "3", "--max-cost-usd", "10"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "gh" in captured.err
    assert "rate limited" in captured.err


def test_gh_fetch_malformed_json_exits_nonzero(monkeypatch, capsys) -> None:
    fake_result = mock.Mock(stdout="{not valid json", stderr="")

    def _fake_run(*args, **kwargs):
        return fake_result

    monkeypatch.setattr(subprocess, "run", _fake_run)

    exit_code = autoship_discover.main(["--max-issues", "3", "--max-cost-usd", "10"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "gh" in captured.err


def test_gh_fetch_success_flows_into_select_eligible_identically_to_input_file(
    monkeypatch, capsys
) -> None:
    issue = _issue(number=7, title="Live-fetched issue")
    fake_result = mock.Mock(stdout=json.dumps([issue]), stderr="")

    captured_argv: list = []

    def _fake_run(argv, **kwargs):
        captured_argv.append(argv)
        return fake_result

    monkeypatch.setattr(subprocess, "run", _fake_run)

    exit_code = autoship_discover.main(["--max-issues", "5", "--max-cost-usd", "10"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == [{"number": 7, "title": "Live-fetched issue"}]

    # Confirm the expected gh invocation shape.
    assert captured_argv
    argv = captured_argv[0]
    assert argv[:3] == ["gh", "issue", "list"]
    assert "--state" in argv and "open" in argv
    assert "--label" in argv and "autoship:ready" in argv
