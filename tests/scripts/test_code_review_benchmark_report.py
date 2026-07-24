"""Unit tests for the #821 benchmark harness's report generator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HARNESS_DIR = Path(__file__).resolve().parents[2] / "evals" / "code-review-benchmark"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

import report


def _write_jsonl(path: Path, records) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in records)


def test_report_recall_math_and_missed_defects(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "results.jsonl",
        [
            {
                "dataset": "bugsjs",
                "project": "Bower",
                "bug_id": "1",
                "hit": True,
                "ground_truth_hunks": [
                    {"file": "lib/a.js", "start_line": 1, "end_line": 2}
                ],
                "findings": [],
                "unmatched_findings": [{"file": "x", "line": 1}],
                "raw_output_path": "r1.txt",
            },
            {
                "dataset": "bugsjs",
                "project": "Bower",
                "bug_id": "2",
                "hit": False,
                "ground_truth_hunks": [
                    {"file": "lib/b.js", "start_line": 5, "end_line": 6}
                ],
                "findings": [],
                "unmatched_findings": [],
                "raw_output_path": "r2.txt",
                "description": "cache bug",
            },
        ],
    )
    _write_jsonl(
        tmp_path / "skipped.jsonl",
        [
            {
                "dataset": "defects4j",
                "project": "Lang",
                "bug_id": "9",
                "skipped": True,
                "reason": "checkout failed",
            }
        ],
    )

    text = report.build_report(tmp_path)

    assert "Overall recall: 1/2 (50%)" in text
    assert "Skipped: 1" in text
    assert "| bugsjs | 1 | 2 | 50% |" in text
    assert "### bugsjs / Bower / bug 2" in text
    assert "lib/b.js:5-6" in text
    assert "cache bug" in text
    assert "Average unmatched findings per hit run: 1.0" in text
    assert "defects4j / Lang / bug 9: checkout failed" in text


def test_report_test_verification_section_when_present(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "results.jsonl",
        [
            {
                "dataset": "bugsjs",
                "project": "Bower",
                "bug_id": "1",
                "hit": True,
                "ground_truth_hunks": [],
                "findings": [],
                "unmatched_findings": [],
                "raw_output_path": "r1.txt",
                "test_verification": {
                    "configured": True,
                    "ran": True,
                    "reproduced": True,
                },
            },
            {
                "dataset": "bugsjs",
                "project": "Bower",
                "bug_id": "2",
                "hit": False,
                "ground_truth_hunks": [],
                "findings": [],
                "unmatched_findings": [],
                "raw_output_path": "r2.txt",
                "test_verification": {
                    "configured": True,
                    "ran": True,
                    "reproduced": False,
                },
            },
        ],
    )
    text = report.build_report(tmp_path)
    assert "## Test verification" in text
    assert "Buggy revision reproduced a failing test: 1/2" in text


def test_report_omits_test_verification_section_when_absent(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "results.jsonl",
        [
            {
                "dataset": "bugsjs",
                "project": "Bower",
                "bug_id": "1",
                "hit": True,
                "ground_truth_hunks": [],
                "findings": [],
                "unmatched_findings": [],
                "raw_output_path": "r1.txt",
            }
        ],
    )
    text = report.build_report(tmp_path)
    assert "## Test verification" not in text


def test_report_no_results_is_well_formed(tmp_path: Path) -> None:
    text = report.build_report(tmp_path)
    assert "Overall recall: n/a (0 attempted)" in text
    assert "None — every attempted bug was hit." in text
    assert "No hit runs to compute noise from." in text


def test_report_total_cost_sums_results_and_skipped(tmp_path: Path) -> None:
    """#1000: total cost is a sum across BOTH results.jsonl and
    skipped.jsonl — a case skipped for "unparseable --json output" still
    paid for a real dispatch."""
    _write_jsonl(
        tmp_path / "results.jsonl",
        [
            {
                "dataset": "defects4j",
                "project": "Lang",
                "bug_id": "29",
                "hit": True,
                "ground_truth_hunks": [],
                "findings": [],
                "unmatched_findings": [],
                "raw_output_path": "r1.txt",
                "cost_usd": 4.48,
            },
            {
                "dataset": "bugsjs",
                "project": "Bower",
                "bug_id": "1",
                "hit": False,
                "ground_truth_hunks": [],
                "findings": [],
                "unmatched_findings": [],
                "raw_output_path": "r2.txt",
                "cost_usd": 1.29,
            },
        ],
    )
    _write_jsonl(
        tmp_path / "skipped.jsonl",
        [
            {
                "dataset": "defects4j",
                "project": "Lang",
                "bug_id": "23",
                "skipped": True,
                "reason": "unparseable --json output",
                "cost_usd": 0.75,
            },
            {
                "dataset": "defects4j",
                "project": "Lang",
                "bug_id": "9",
                "skipped": True,
                "reason": "checkout failed",
                "cost_usd": None,
            },
        ],
    )

    text = report.build_report(tmp_path)
    assert "Total cost: $6.52" in text


def test_report_total_cost_defaults_missing_field_to_zero(tmp_path: Path) -> None:
    """Records with no `cost_usd` key at all (older results, pre-#1000)
    must not crash the report — they contribute $0.00."""
    _write_jsonl(
        tmp_path / "results.jsonl",
        [
            {
                "dataset": "bugsjs",
                "project": "Bower",
                "bug_id": "1",
                "hit": True,
                "ground_truth_hunks": [],
                "findings": [],
                "unmatched_findings": [],
                "raw_output_path": "r1.txt",
            }
        ],
    )
    text = report.build_report(tmp_path)
    assert "Total cost: $0.00" in text


def test_write_report_creates_results_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "results"
    path = report.write_report(target)
    assert path.is_file()
    assert path.parent == target
