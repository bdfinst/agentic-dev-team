"""Tests for autoship_group.py (Slice 1 grouping — native-dependency and
shared-parent signals only; shared-label and --max-batch-size are later
steps, not covered here)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import autoship_group


def _issue(**overrides) -> dict:
    base = {
        "number": 1,
        "title": "Some issue",
        "state": "OPEN",
        "createdAt": "2026-07-01T00:00:00Z",
        "labels": [{"name": "autoship:ready"}],
        "closedByPullRequestsReferences": [],
        "subIssuesSummary": {"total": 0},
        "blockedBy": [],
        "blocking": [],
        "parent": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# CLI wiring — build_parser default/label override, --input-file test seam
# ---------------------------------------------------------------------------


def test_label_defaults_to_autoship_ready() -> None:
    args = autoship_group.build_parser().parse_args([])
    assert args.label == "autoship:ready"


def test_label_override() -> None:
    args = autoship_group.build_parser().parse_args(["--label", "custom-label"])
    assert args.label == "custom-label"


def test_input_file_bypasses_gh_invocation(tmp_path, monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise AssertionError(
            "subprocess.run must not be called when --input-file is given"
        )

    monkeypatch.setattr(subprocess, "run", _raise)

    fixture = tmp_path / "issues.json"
    fixture.write_text(json.dumps([_issue()]), encoding="utf-8")

    exit_code = autoship_group.main(["--input-file", str(fixture)])
    assert exit_code == 0


# ---------------------------------------------------------------------------
# Slice 1 grouping scenarios
# ---------------------------------------------------------------------------


def test_native_dependency_groups_two_issues_via_blockedby() -> None:
    issue_a = _issue(
        number=10,
        title="A",
        createdAt="2026-07-01T00:00:00Z",
        blockedBy=[{"number": 11}],
    )
    issue_b = _issue(number=11, title="B", createdAt="2026-07-02T00:00:00Z")
    issue_c = _issue(number=12, title="C, unrelated", createdAt="2026-07-03T00:00:00Z")

    result = autoship_group.group_issues([issue_a, issue_b, issue_c])

    assert len(result["batches"]) == 1
    batch = result["batches"][0]
    assert batch["batch_id"] == "grp-10"
    assert [m["number"] for m in batch["members"]] == [10, 11]
    assert [m["number"] for m in result["ungrouped"]] == [12]


def test_blockedby_edge_to_ineligible_issue_leaves_referencer_ungrouped() -> None:
    # Issue #999 is not present in the eligible input set at all — simulating
    # upstream filtering having already excluded it (e.g. an open linked PR).
    issue_a = _issue(number=20, title="A", blockedBy=[{"number": 999}])

    result = autoship_group.group_issues([issue_a])

    assert result["batches"] == []
    assert [m["number"] for m in result["ungrouped"]] == [20]


def test_shared_parent_groups_three_issues_into_one_batch() -> None:
    issue_a = _issue(
        number=30, title="A", createdAt="2026-07-03T00:00:00Z", parent={"number": 1}
    )
    issue_b = _issue(
        number=31, title="B", createdAt="2026-07-01T00:00:00Z", parent={"number": 1}
    )
    issue_c = _issue(
        number=32, title="C", createdAt="2026-07-02T00:00:00Z", parent={"number": 1}
    )

    result = autoship_group.group_issues([issue_a, issue_b, issue_c])

    assert len(result["batches"]) == 1
    batch = result["batches"][0]
    # Oldest member by createdAt is #31 (2026-07-01) — batch_id derives from it.
    assert batch["batch_id"] == "grp-31"
    assert {m["number"] for m in batch["members"]} == {30, 31, 32}
    assert result["ungrouped"] == []


def test_shared_parent_groups_without_any_blocking_fields_present() -> None:
    # No blockedBy/blocking keys at all — has_shared_parent must not depend
    # on their presence.
    issue_a = _issue(number=40, title="A", parent={"number": 5})
    issue_b = _issue(number=41, title="B", parent={"number": 5})
    del issue_a["blockedBy"]
    del issue_a["blocking"]
    del issue_b["blockedBy"]
    del issue_b["blocking"]

    result = autoship_group.group_issues([issue_a, issue_b])

    assert len(result["batches"]) == 1
    assert {m["number"] for m in result["batches"][0]["members"]} == {40, 41}
    assert result["ungrouped"] == []


def test_no_shared_signal_all_issues_ungrouped() -> None:
    issue_a = _issue(number=50, title="A")
    issue_b = _issue(number=51, title="B")
    issue_c = _issue(number=52, title="C")

    result = autoship_group.group_issues([issue_a, issue_b, issue_c])

    assert result["batches"] == []
    assert {m["number"] for m in result["ungrouped"]} == {50, 51, 52}
