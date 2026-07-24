"""Unit tests for hooks/lib/run_report.py (#1167).

Covers:
  - joins all three streams (boundary-events, cost-metering, workflow-states)
    for a given session_id.
  - handles missing streams gracefully (absent file -> empty section, not an
    error).
  - auto-detects the most recent session_id when --session is omitted.
  - groups denials by matched_rule (cause) for block/warn decisions.
  - the cost join is explicitly marked unjoinable, never guessed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_HOOKS_DIR = _PLUGIN_DIR / "hooks"
_LIB_DIR = _HOOKS_DIR / "lib"
_LIB_SCRIPT = _LIB_DIR / "run_report.py"

for _p in (_HOOKS_DIR, _LIB_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import run_report  # type: ignore[import-not-found]
import workflow_state  # type: ignore[import-not-found]


def _write_jsonl(path: Path, entries: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def _boundary_event(session_id: str, decision: str, matched_rule: str, ts: str) -> dict:
    return {
        "ts": ts,
        "hook": "destructive_guard",
        "tool": "Bash",
        "decision": decision,
        "matched_rule": matched_rule,
        "session_id": session_id,
    }


# ---------------------------------------------------------------------------
# Joins all three streams
# ---------------------------------------------------------------------------


def test_build_report_joins_workflow_and_boundary_streams(tmp_path: Path) -> None:
    workflow_state.emit_state_transition(tmp_path, "ship", None, "SPEC", "sess-1")
    workflow_state.emit_state_transition(tmp_path, "ship", "SPEC", "PLAN", "sess-1")

    _write_jsonl(
        tmp_path / "metrics" / "boundary-events.jsonl",
        [
            _boundary_event("sess-1", "block", "no-force-push", "2026-01-01T00:00:00Z"),
            _boundary_event("sess-1", "bypass", "no-verify", "2026-01-01T00:01:00Z"),
        ],
    )
    _write_jsonl(
        tmp_path / "metrics" / "cost-metering.jsonl",
        [{"timestamp": "2026-01-01T00:02:00Z", "transcript": "t.jsonl",
          "total": {"cost_usd": 1.23}}],
    )

    report = run_report.build_report(tmp_path, session_id="sess-1")

    assert report["session_id"] == "sess-1"
    assert report["current_state"] == "PLAN"
    assert "SPEC" in report["dwell_seconds"]
    assert report["rejection_count"] == 1
    assert report["bypass_count"] == 1
    assert report["cost"]["joinable"] is False


# ---------------------------------------------------------------------------
# Missing streams
# ---------------------------------------------------------------------------


def test_build_report_handles_all_streams_missing(tmp_path: Path) -> None:
    report = run_report.build_report(tmp_path, session_id="sess-none")

    assert report["session_id"] == "sess-none"
    assert report["current_state"] is None
    assert report["dwell_seconds"] == {}
    assert report["rejection_count"] == 0
    assert report["bypass_count"] == 0
    assert report["denials_by_cause"] == {}
    assert report["cost"]["joinable"] is False
    assert "no cost-metering.jsonl" in report["cost"]["reason"]


def test_build_report_handles_partial_streams(tmp_path: Path) -> None:
    workflow_state.emit_state_transition(tmp_path, "build", None, "BUILD", "sess-2")

    report = run_report.build_report(tmp_path, session_id="sess-2")

    assert report["current_state"] == "BUILD"
    assert report["rejection_count"] == 0
    assert report["bypass_count"] == 0


# ---------------------------------------------------------------------------
# Auto-detect most recent session
# ---------------------------------------------------------------------------


def test_build_report_auto_detects_most_recent_session(tmp_path: Path) -> None:
    workflow_state.emit_state_transition(tmp_path, "ship", None, "SPEC", "sess-a")
    workflow_state.emit_state_transition(tmp_path, "ship", None, "PLAN", "sess-b")

    report = run_report.build_report(tmp_path, session_id=None)

    assert report["session_id"] == "sess-b"
    assert report["current_state"] == "PLAN"


def test_build_report_auto_detect_with_no_sessions_at_all(tmp_path: Path) -> None:
    report = run_report.build_report(tmp_path, session_id=None)
    assert report["session_id"] is None
    assert report["current_state"] is None


# ---------------------------------------------------------------------------
# Denials grouped by cause
# ---------------------------------------------------------------------------


def test_denials_by_cause_groups_block_and_warn_not_bypass(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "metrics" / "boundary-events.jsonl",
        [
            _boundary_event("sess-3", "block", "no-force-push", "2026-01-01T00:00:00Z"),
            _boundary_event("sess-3", "block", "no-force-push", "2026-01-01T00:01:00Z"),
            _boundary_event("sess-3", "warn", "large-diff", "2026-01-01T00:02:00Z"),
            _boundary_event("sess-3", "bypass", "no-verify", "2026-01-01T00:03:00Z"),
        ],
    )

    report = run_report.build_report(tmp_path, session_id="sess-3")

    assert report["denials_by_cause"] == {"no-force-push": 2, "large-diff": 1}
    assert report["rejection_count"] == 2
    assert report["bypass_count"] == 1


def test_denials_by_cause_filters_to_requested_session(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "metrics" / "boundary-events.jsonl",
        [
            _boundary_event("sess-x", "block", "rule-x", "2026-01-01T00:00:00Z"),
            _boundary_event("sess-y", "block", "rule-y", "2026-01-01T00:01:00Z"),
        ],
    )

    report = run_report.build_report(tmp_path, session_id="sess-x")

    assert report["denials_by_cause"] == {"rule-x": 1}
    assert report["rejection_count"] == 1


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------


def test_cli_report_prints_json(tmp_path: Path) -> None:
    workflow_state.emit_state_transition(tmp_path, "ship", None, "SPEC", "sess-cli")

    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "report",
            "--cwd",
            str(tmp_path),
            "--session",
            "sess-cli",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["session_id"] == "sess-cli"
    assert report["current_state"] == "SPEC"
