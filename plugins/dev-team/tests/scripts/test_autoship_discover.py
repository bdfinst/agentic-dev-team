"""Tests for autoship_discover.py (#989)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import autoship_discover  # noqa: E402


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
