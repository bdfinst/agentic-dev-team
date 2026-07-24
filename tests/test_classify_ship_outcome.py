"""
Tests for plugins/dev-team/hooks/lib/classify_ship_outcome.py
"""

import json
import subprocess
import sys
from pathlib import Path

# Resolve module path without installing the package.
LIB_DIR = Path(__file__).parent.parent / "plugins" / "dev-team" / "hooks" / "lib"
sys.path.insert(0, str(LIB_DIR))

from classify_ship_outcome import classify

SINCE = "2024-01-15T10:00:00Z"
BEFORE = "2024-01-15T09:00:00Z"
AT = "2024-01-15T10:00:00Z"
AFTER = "2024-01-15T11:00:00Z"

MODULE_PATH = LIB_DIR / "classify_ship_outcome.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_jsonl(path: Path, records: list) -> None:
    with path.open("w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# (a) convergence_failure when escalated entry present
# ---------------------------------------------------------------------------

def test_convergence_failure_when_escalated(tmp_path):
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [{"timestamp": AFTER, "outcome": "escalated"}])
    write_jsonl(vl, [{"timestamp": AFTER, "outcome": "ran"}])

    assert classify(rv, vl, SINCE) == "convergence_failure"


def test_convergence_failure_takes_priority_over_success(tmp_path):
    """escalated in review-value wins even when verify-log shows 'ran'."""
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [{"timestamp": AFTER, "outcome": "escalated"}])
    write_jsonl(vl, [{"timestamp": AFTER, "outcome": "ran"}])

    assert classify(rv, vl, SINCE) == "convergence_failure"


# ---------------------------------------------------------------------------
# (b) success when verify entry with outcome "ran" present
# ---------------------------------------------------------------------------

def test_success_when_ran(tmp_path):
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [{"timestamp": AFTER, "outcome": "passed"}])
    write_jsonl(vl, [{"timestamp": AFTER, "outcome": "ran"}])

    assert classify(rv, vl, SINCE) == "success"


# ---------------------------------------------------------------------------
# (c) success when outcome is "failed-then-fixed"
# ---------------------------------------------------------------------------

def test_success_when_failed_then_fixed(tmp_path):
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [])
    write_jsonl(vl, [{"timestamp": AFTER, "outcome": "failed-then-fixed"}])

    assert classify(rv, vl, SINCE) == "success"


# ---------------------------------------------------------------------------
# (d) unrecognized when no matching entries
# ---------------------------------------------------------------------------

def test_unrecognized_when_no_matching_entries(tmp_path):
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [{"timestamp": AFTER, "outcome": "passed"}])
    write_jsonl(vl, [{"timestamp": AFTER, "outcome": "skipped"}])

    assert classify(rv, vl, SINCE) == "unrecognized"


def test_unrecognized_when_both_files_empty(tmp_path):
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [])
    write_jsonl(vl, [])

    assert classify(rv, vl, SINCE) == "unrecognized"


# ---------------------------------------------------------------------------
# (e) lines before since_iso are ignored
# ---------------------------------------------------------------------------

def test_lines_before_since_iso_ignored_for_escalated(tmp_path):
    """An 'escalated' entry timestamped before since_iso must not trigger failure."""
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [{"timestamp": BEFORE, "outcome": "escalated"}])
    write_jsonl(vl, [{"timestamp": AFTER, "outcome": "ran"}])

    assert classify(rv, vl, SINCE) == "success"


def test_lines_before_since_iso_ignored_for_ran(tmp_path):
    """A 'ran' entry before since_iso must not trigger success."""
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [])
    write_jsonl(vl, [{"timestamp": BEFORE, "outcome": "ran"}])

    assert classify(rv, vl, SINCE) == "unrecognized"


def test_records_at_since_iso_are_included(tmp_path):
    """Records with timestamp == since_iso are included (boundary is inclusive)."""
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [])
    write_jsonl(vl, [{"timestamp": AT, "outcome": "ran"}])

    assert classify(rv, vl, SINCE) == "success"


# ---------------------------------------------------------------------------
# (f) missing files treated as empty
# ---------------------------------------------------------------------------

def test_missing_review_value_treated_as_empty(tmp_path):
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(vl, [{"timestamp": AFTER, "outcome": "ran"}])

    assert classify(tmp_path / "nonexistent.jsonl", vl, SINCE) == "success"


def test_missing_verify_log_treated_as_empty(tmp_path):
    rv = tmp_path / "review-value.jsonl"
    write_jsonl(rv, [{"timestamp": AFTER, "outcome": "passed"}])

    assert classify(rv, tmp_path / "nonexistent.jsonl", SINCE) == "unrecognized"


def test_both_files_missing(tmp_path):
    assert classify(
        tmp_path / "no-rv.jsonl",
        tmp_path / "no-vl.jsonl",
        SINCE,
    ) == "unrecognized"


# ---------------------------------------------------------------------------
# Alternate timestamp field names
# ---------------------------------------------------------------------------

def test_logged_at_field_respected(tmp_path):
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [{"logged_at": BEFORE, "outcome": "escalated"}])
    write_jsonl(vl, [{"logged_at": AFTER, "outcome": "ran"}])

    # escalated is before since_iso, so should not trigger convergence_failure
    assert classify(rv, vl, SINCE) == "success"


def test_ts_field_respected(tmp_path):
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [])
    write_jsonl(vl, [{"ts": AFTER, "outcome": "ran"}])

    assert classify(rv, vl, SINCE) == "success"


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

def test_cli_prints_result(tmp_path):
    rv = tmp_path / "review-value.jsonl"
    vl = tmp_path / "verify-log.jsonl"
    write_jsonl(rv, [])
    write_jsonl(vl, [{"timestamp": AFTER, "outcome": "ran"}])

    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--review-value", str(rv),
            "--verify-log", str(vl),
            "--since", SINCE,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "success"
