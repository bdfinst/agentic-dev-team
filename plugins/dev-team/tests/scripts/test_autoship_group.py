"""Tests for autoship_group.py (Slice 1 grouping — native-dependency,
shared-parent, and shared-label signals, plus --max-batch-size trimming)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_input_file_without_optional_dependency_fields_is_accepted(tmp_path) -> None:
    # blockedBy/blocking/parent are optional enrichment, not required schema
    # — a fixture omitting them entirely must not be rejected as malformed.
    issue = _issue()
    del issue["blockedBy"]
    del issue["blocking"]
    del issue["parent"]

    fixture = tmp_path / "issues.json"
    fixture.write_text(json.dumps([issue]), encoding="utf-8")

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


def test_native_dependency_groups_via_real_gh_connection_object_shape() -> None:
    # A live `gh issue list --json blockedBy,blocking` returns a GraphQL
    # connection object shaped {"nodes": [...], "totalCount": N} — NOT a
    # bare list. `_referenced_numbers` must unwrap this shape rather than
    # silently iterating the dict's keys ("nodes", "totalCount") and
    # finding zero matches.
    issue_a = _issue(
        number=13,
        title="A",
        createdAt="2026-07-01T00:00:00Z",
        blockedBy={"nodes": [{"number": 14}], "totalCount": 1},
    )
    issue_b = _issue(number=14, title="B", createdAt="2026-07-02T00:00:00Z")

    result = autoship_group.group_issues([issue_a, issue_b])

    assert len(result["batches"]) == 1
    batch = result["batches"][0]
    assert batch["batch_id"] == "grp-13"
    assert {m["number"] for m in batch["members"]} == {13, 14}
    assert result["ungrouped"] == []


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
    # Distinct non-autoship labels on each issue (plus the shared
    # "autoship:ready" label every eligible issue carries by definition)
    # confirm has_shared_label doesn't spuriously fire alongside the other
    # two signals when nothing is actually shared.
    issue_a = _issue(
        number=50, title="A", labels=[{"name": "autoship:ready"}, {"name": "area:a"}]
    )
    issue_b = _issue(
        number=51, title="B", labels=[{"name": "autoship:ready"}, {"name": "area:b"}]
    )
    issue_c = _issue(
        number=52, title="C", labels=[{"name": "autoship:ready"}, {"name": "area:c"}]
    )

    result = autoship_group.group_issues([issue_a, issue_b, issue_c])

    assert result["batches"] == []
    assert {m["number"] for m in result["ungrouped"]} == {50, 51, 52}


def test_shared_non_autoship_label_groups_two_issues() -> None:
    issue_a = _issue(
        number=60,
        title="A",
        createdAt="2026-07-01T00:00:00Z",
        labels=[{"name": "autoship:ready"}, {"name": "area:ci"}],
    )
    issue_b = _issue(
        number=61,
        title="B",
        createdAt="2026-07-02T00:00:00Z",
        labels=[{"name": "autoship:ready"}, {"name": "area:ci"}],
    )
    issue_c = _issue(number=62, title="C, unrelated", createdAt="2026-07-03T00:00:00Z")

    result = autoship_group.group_issues([issue_a, issue_b, issue_c])

    assert len(result["batches"]) == 1
    batch = result["batches"][0]
    assert batch["batch_id"] == "grp-60"
    assert [m["number"] for m in batch["members"]] == [60, 61]
    assert [m["number"] for m in result["ungrouped"]] == [62]


def test_shared_autoship_prefixed_label_alone_does_not_group() -> None:
    # Every eligible issue carries "autoship:ready" by definition — that
    # shared label alone must never be enough for has_shared_label to fire.
    issue_a = _issue(number=70, title="A", labels=[{"name": "autoship:ready"}])
    issue_b = _issue(number=71, title="B", labels=[{"name": "autoship:ready"}])

    result = autoship_group.group_issues([issue_a, issue_b])

    assert result["batches"] == []
    assert {m["number"] for m in result["ungrouped"]} == {70, 71}


def test_custom_freeform_label_alone_does_not_group_the_whole_pool() -> None:
    # A `--label` value with no "autoship:" prefix (e.g. `--label
    # ready-to-ship`) is still the label every eligible issue carries by
    # construction — it must be excluded from has_shared_label the same way
    # the autoship:* prefix is, or the entire eligible pool collapses into
    # one batch.
    issue_a = _issue(number=100, title="A", labels=[{"name": "custom-label"}])
    issue_b = _issue(number=101, title="B", labels=[{"name": "custom-label"}])
    issue_c = _issue(number=102, title="C", labels=[{"name": "custom-label"}])

    result = autoship_group.group_issues(
        [issue_a, issue_b, issue_c], label="custom-label"
    )

    assert result["batches"] == []
    assert {m["number"] for m in result["ungrouped"]} == {100, 101, 102}


def test_custom_label_still_groups_on_a_genuinely_shared_other_label() -> None:
    # Sharing the eligibility label never groups; sharing a THIRD label still
    # does — confirms the exclusion is scoped to exactly the configured
    # label, not a false negative on every shared-label case.
    issue_a = _issue(
        number=110,
        title="A",
        createdAt="2026-07-01T00:00:00Z",
        labels=[{"name": "custom-label"}, {"name": "area:ci"}],
    )
    issue_b = _issue(
        number=111,
        title="B",
        createdAt="2026-07-02T00:00:00Z",
        labels=[{"name": "custom-label"}, {"name": "area:ci"}],
    )

    result = autoship_group.group_issues([issue_a, issue_b], label="custom-label")

    assert len(result["batches"]) == 1
    assert result["batches"][0]["batch_id"] == "grp-110"


# ---------------------------------------------------------------------------
# --max-batch-size trimming
# ---------------------------------------------------------------------------


def _labeled_issue(number: int, day: int) -> dict:
    return _issue(
        number=number,
        title=f"Issue {number}",
        createdAt=f"2026-07-{day:02d}T00:00:00Z",
        labels=[{"name": "autoship:ready"}, {"name": "area:shared"}],
    )


def test_batch_over_cap_trims_to_oldest_n_and_overflows_the_rest() -> None:
    issues = [_labeled_issue(number=80 + i, day=i + 1) for i in range(6)]

    result = autoship_group.group_issues(issues, max_batch_size=5)

    assert len(result["batches"]) == 1
    batch = result["batches"][0]
    assert batch["batch_id"] == "grp-80"
    assert [m["number"] for m in batch["members"]] == [80, 81, 82, 83, 84]
    assert [m["number"] for m in result["ungrouped"]] == [85]


def test_batch_exactly_at_cap_is_not_trimmed() -> None:
    issues = [_labeled_issue(number=90 + i, day=i + 1) for i in range(5)]

    result = autoship_group.group_issues(issues, max_batch_size=5)

    assert len(result["batches"]) == 1
    batch = result["batches"][0]
    assert batch["batch_id"] == "grp-90"
    assert [m["number"] for m in batch["members"]] == [90, 91, 92, 93, 94]
    assert result["ungrouped"] == []


@pytest.mark.parametrize("bad_value", ["0", "-1"])
def test_max_batch_size_zero_or_negative_is_rejected(bad_value: str) -> None:
    with pytest.raises(SystemExit):
        autoship_group.build_parser().parse_args(["--max-batch-size", bad_value])


def test_max_batch_size_one_routes_trimmed_group_to_ungrouped_not_a_batch() -> None:
    # A 2-member group trimmed to max_batch_size=1 must land entirely in
    # ungrouped, matching the untrimmed len(members) == 1 case — never
    # emitted as a 1-member "batch".
    issue_a = _issue(
        number=120, title="A", createdAt="2026-07-01T00:00:00Z", parent={"number": 9}
    )
    issue_b = _issue(
        number=121, title="B", createdAt="2026-07-02T00:00:00Z", parent={"number": 9}
    )

    result = autoship_group.group_issues([issue_a, issue_b], max_batch_size=1)

    assert result["batches"] == []
    assert {m["number"] for m in result["ungrouped"]} == {120, 121}


# ---------------------------------------------------------------------------
# createdAt tie-break determinism
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Step 4.3 — has_batch_confirmed_override (confirmed-batch signal)
# ---------------------------------------------------------------------------


def test_batch_confirmed_override_unions_two_mutually_confirmed_issues() -> None:
    issue_a = _issue(
        number=300,
        title="A",
        labels=[{"name": "autoship:ready"}, {"name": "autoship:batch-confirmed"}],
        confirmed_batch_members=[301],
    )
    issue_b = _issue(
        number=301,
        title="B",
        labels=[{"name": "autoship:ready"}, {"name": "autoship:batch-confirmed"}],
        confirmed_batch_members=[300],
    )

    result = autoship_group.group_issues([issue_a, issue_b])

    assert len(result["batches"]) == 1
    assert {m["number"] for m in result["batches"][0]["members"]} == {300, 301}
    assert result["ungrouped"] == []


def test_batch_confirmed_override_does_not_union_when_only_one_is_confirmed() -> None:
    # Issue B never received `autoship:batch-confirmed` — the signal must
    # never fire on a one-sided confirmation.
    issue_a = _issue(
        number=310,
        title="A",
        labels=[{"name": "autoship:ready"}, {"name": "autoship:batch-confirmed"}],
        confirmed_batch_members=[311],
    )
    issue_b = _issue(number=311, title="B", labels=[{"name": "autoship:ready"}])

    result = autoship_group.group_issues([issue_a, issue_b])

    assert result["batches"] == []
    assert {m["number"] for m in result["ungrouped"]} == {310, 311}


def test_batch_confirmed_override_does_not_union_on_marker_mismatch() -> None:
    # Partial confirmation: both carry autoship:batch-confirmed, but B's
    # confirmed_batch_members no longer lists A (e.g. B was confirmed as
    # part of a different subset of the original proposal) — the signal
    # must require BOTH sides to still cross-reference each other.
    issue_a = _issue(
        number=320,
        title="A",
        labels=[{"name": "autoship:ready"}, {"name": "autoship:batch-confirmed"}],
        confirmed_batch_members=[321],
    )
    issue_b = _issue(
        number=321,
        title="B",
        labels=[{"name": "autoship:ready"}, {"name": "autoship:batch-confirmed"}],
        confirmed_batch_members=[999],
    )

    result = autoship_group.group_issues([issue_a, issue_b])

    assert result["batches"] == []
    assert {m["number"] for m in result["ungrouped"]} == {320, 321}


def test_identical_createdat_tie_breaks_by_issue_number() -> None:
    # Both members share the exact same createdAt — the sort must still be
    # deterministic via a secondary key (issue number), not input order.
    issue_a = _issue(
        number=202,
        title="A",
        createdAt="2026-07-01T00:00:00Z",
        parent={"number": 1},
    )
    issue_b = _issue(
        number=201,
        title="B",
        createdAt="2026-07-01T00:00:00Z",
        parent={"number": 1},
    )

    result = autoship_group.group_issues([issue_a, issue_b])

    assert len(result["batches"]) == 1
    batch = result["batches"][0]
    assert batch["batch_id"] == "grp-201"
    assert [m["number"] for m in batch["members"]] == [201, 202]
