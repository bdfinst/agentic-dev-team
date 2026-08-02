"""Tests for autoship_queue.py (Slice 2 — --max-issues-capped, whole-batch-
or-defer dispatch-queue construction)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import autoship_queue


def _batch(batch_id: str, members: list[dict]) -> dict:
    return {"batch_id": batch_id, "members": members}


def _member(number: int, created_at: str, title: str = "Some issue") -> dict:
    return {"number": number, "title": title, "createdAt": created_at}


# ---------------------------------------------------------------------------
# Plan Gherkin scenarios (Step 2.1)
# ---------------------------------------------------------------------------


def test_all_batches_and_solo_entries_fit_under_the_cap() -> None:
    grouping_output = {
        "batches": [
            _batch(
                "grp-1",
                [
                    _member(1, "2026-07-01T00:00:00Z"),
                    _member(2, "2026-07-02T00:00:00Z"),
                ],
            )
        ],
        "ungrouped": [_member(3, "2026-07-03T00:00:00Z")],
    }

    result = autoship_queue.build_queue(grouping_output, max_issues=10)

    assert result["queue"] == [
        {"type": "batch", "batch_id": "grp-1", "issues": [1, 2]},
        {"type": "solo", "issue": 3},
    ]
    assert result["deferred"] == []


def test_batch_that_would_exceed_remaining_cap_is_deferred_whole_and_scan_continues() -> (
    None
):
    grouping_output = {
        "batches": [
            _batch(
                "grp-20",
                [
                    _member(20, "2026-07-02T00:00:00Z"),
                    _member(21, "2026-07-02T00:00:00Z"),
                    _member(22, "2026-07-02T00:00:00Z"),
                    _member(23, "2026-07-02T00:00:00Z"),
                    _member(24, "2026-07-02T00:00:00Z"),
                ],
            )
        ],
        "ungrouped": [
            _member(10, "2026-07-01T00:00:00Z"),
            _member(30, "2026-07-03T00:00:00Z"),
        ],
    }

    # Oldest-first order: solo #10, batch grp-20 (5 issues), solo #30.
    # max_issues=3: solo #10 fits (running=1); the 5-issue batch would push
    # to 6 > 3, so it's deferred whole; the scan continues to solo #30,
    # which still fits (running=2).
    result = autoship_queue.build_queue(grouping_output, max_issues=3)

    assert result["queue"] == [
        {"type": "solo", "issue": 10},
        {"type": "solo", "issue": 30},
    ]
    assert result["deferred"] == [
        {"type": "batch", "batch_id": "grp-20", "issues": [20, 21, 22, 23, 24]}
    ]


def test_cap_reached_exactly_by_a_solo_issue_admits_no_further_entries() -> None:
    grouping_output = {
        "batches": [],
        "ungrouped": [
            _member(1, "2026-07-01T00:00:00Z"),
            _member(2, "2026-07-02T00:00:00Z"),
            _member(3, "2026-07-03T00:00:00Z"),
        ],
    }

    result = autoship_queue.build_queue(grouping_output, max_issues=2)

    assert result["queue"] == [
        {"type": "solo", "issue": 1},
        {"type": "solo", "issue": 2},
    ]
    assert result["deferred"] == [{"type": "solo", "issue": 3}]


def test_no_eligible_entries_produces_empty_queue_and_deferred() -> None:
    grouping_output = {"batches": [], "ungrouped": []}

    result = autoship_queue.build_queue(grouping_output, max_issues=10)

    assert result == {"queue": [], "deferred": []}


def test_single_solo_issue_under_the_cap_appears_as_a_solo_unit() -> None:
    grouping_output = {
        "batches": [],
        "ungrouped": [_member(42, "2026-07-01T00:00:00Z")],
    }

    result = autoship_queue.build_queue(grouping_output, max_issues=5)

    assert result["queue"] == [{"type": "solo", "issue": 42}]
    assert result["deferred"] == []


# ---------------------------------------------------------------------------
# Cross-script contract: autoship_group.py's actual stdout -> autoship_queue.py
# ---------------------------------------------------------------------------


def _eligible_issue(number: int, created_at: str, **overrides) -> dict:
    base = {
        "number": number,
        "title": f"Issue {number}",
        "state": "OPEN",
        "createdAt": created_at,
        "labels": [{"name": "autoship:ready"}],
        "closedByPullRequestsReferences": [],
        "subIssuesSummary": {"total": 0},
    }
    base.update(overrides)
    return base


def test_identical_created_at_across_units_tie_breaks_by_issue_number() -> None:
    # A solo issue and a batch share the exact same createdAt — the sort
    # must still be deterministic via the tie-break (ascending issue
    # number), not input/construction order. Batch grp-5 is keyed off its
    # oldest member, #5; solo #3 has the lower number and must sort first.
    grouping_output = {
        "batches": [
            _batch(
                "grp-5",
                [
                    _member(5, "2026-07-01T00:00:00Z"),
                    _member(6, "2026-07-02T00:00:00Z"),
                ],
            )
        ],
        "ungrouped": [_member(3, "2026-07-01T00:00:00Z")],
    }

    result = autoship_queue.build_queue(grouping_output, max_issues=10)

    assert result["queue"] == [
        {"type": "solo", "issue": 3},
        {"type": "batch", "batch_id": "grp-5", "issues": [5, 6]},
    ]
    assert result["deferred"] == []


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def test_max_issues_is_required() -> None:
    with pytest.raises(SystemExit):
        autoship_queue.build_parser().parse_args([])


@pytest.mark.parametrize("bad_value", ["0", "-1"])
def test_max_issues_zero_or_negative_is_rejected(bad_value: str) -> None:
    with pytest.raises(SystemExit):
        autoship_queue.build_parser().parse_args(["--max-issues", bad_value])


def test_valid_max_issues_with_input_file_parses_and_runs_end_to_end(
    tmp_path, capsys
) -> None:
    fixture = tmp_path / "grouping-output.json"
    fixture.write_text(
        json.dumps(
            {
                "batches": [],
                "ungrouped": [_member(1, "2026-07-01T00:00:00Z")],
            }
        ),
        encoding="utf-8",
    )

    exit_code = autoship_queue.main(
        ["--max-issues", "10", "--input-file", str(fixture)]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "queue": [{"type": "solo", "issue": 1}],
        "deferred": [],
    }


def test_nonexistent_input_file_is_a_clean_error(capsys) -> None:
    exit_code = autoship_queue.main(
        ["--max-issues", "10", "--input-file", "/nonexistent/path/does-not-exist.json"]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "autoship_queue:" in captured.err


def test_invalid_json_input_file_is_a_clean_error(tmp_path, capsys) -> None:
    fixture = tmp_path / "bad.json"
    fixture.write_text("{not valid json", encoding="utf-8")

    exit_code = autoship_queue.main(
        ["--max-issues", "10", "--input-file", str(fixture)]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "autoship_queue:" in captured.err
    assert "not valid JSON" in captured.err


def test_non_dict_top_level_payload_is_a_clean_error(tmp_path, capsys) -> None:
    fixture = tmp_path / "list.json"
    fixture.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    exit_code = autoship_queue.main(
        ["--max-issues", "10", "--input-file", str(fixture)]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "autoship_queue:" in captured.err
    assert "must be a JSON object" in captured.err


def test_missing_batches_key_is_a_clean_error(tmp_path, capsys) -> None:
    # Fix 5 (autoship-issue-batching full-feature review): a malformed
    # rewrite of <scratch-grouping.json> between Step 2b/2c and
    # autoship_queue.py that drops a top-level key must surface as an
    # error, not silently default to an empty list.
    fixture = tmp_path / "grouping-output.json"
    fixture.write_text(json.dumps({"ungrouped": []}), encoding="utf-8")

    exit_code = autoship_queue.main(
        ["--max-issues", "10", "--input-file", str(fixture)]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "autoship_queue:" in captured.err
    assert '"batches"' in captured.err


def test_missing_ungrouped_key_is_a_clean_error(tmp_path, capsys) -> None:
    fixture = tmp_path / "grouping-output.json"
    fixture.write_text(json.dumps({"batches": []}), encoding="utf-8")

    exit_code = autoship_queue.main(
        ["--max-issues", "10", "--input-file", str(fixture)]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "autoship_queue:" in captured.err
    assert '"ungrouped"' in captured.err


def test_batch_missing_members_is_a_clean_error(tmp_path, capsys) -> None:
    fixture = tmp_path / "grouping-output.json"
    fixture.write_text(
        json.dumps({"batches": [{"batch_id": "grp-1"}], "ungrouped": []}),
        encoding="utf-8",
    )

    exit_code = autoship_queue.main(
        ["--max-issues", "10", "--input-file", str(fixture)]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "autoship_queue:" in captured.err
    assert "grp-1" in captured.err
    assert "members" in captured.err


def test_ungrouped_entry_missing_created_at_is_a_clean_error(tmp_path, capsys) -> None:
    fixture = tmp_path / "grouping-output.json"
    fixture.write_text(
        json.dumps({"batches": [], "ungrouped": [{"number": 7}]}),
        encoding="utf-8",
    )

    exit_code = autoship_queue.main(
        ["--max-issues", "10", "--input-file", str(fixture)]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "autoship_queue:" in captured.err
    assert "#7" in captured.err
    assert "createdAt" in captured.err


def test_group_then_queue_pipeline_composes_without_drift(tmp_path) -> None:
    group_script = _SCRIPTS_DIR / "autoship_group.py"
    queue_script = _SCRIPTS_DIR / "autoship_queue.py"

    # Two issues sharing a native parent (a grouping signal) plus one
    # unrelated issue that stays solo.
    fixture = tmp_path / "eligible.json"
    fixture.write_text(
        json.dumps(
            [
                _eligible_issue(201, "2026-07-01T00:00:00Z", parent={"number": 9}),
                _eligible_issue(202, "2026-07-02T00:00:00Z", parent={"number": 9}),
                _eligible_issue(203, "2026-07-03T00:00:00Z"),
            ]
        ),
        encoding="utf-8",
    )

    group_result = subprocess.run(
        [sys.executable, str(group_script), "--input-file", str(fixture)],
        capture_output=True,
        text=True,
        check=True,
    )

    # Feed autoship_group.py's actual stdout, unmodified, into
    # autoship_queue.py via stdin — the real pipeline's own wiring.
    queue_result = subprocess.run(
        [sys.executable, str(queue_script), "--max-issues", "10"],
        input=group_result.stdout,
        capture_output=True,
        text=True,
        check=True,
    )
    queue_output = json.loads(queue_result.stdout)

    assert queue_output["queue"] == [
        {"type": "batch", "batch_id": "grp-201", "issues": [201, 202]},
        {"type": "solo", "issue": 203},
    ]
    assert queue_output["deferred"] == []
