"""Unit tests for hooks/lib/workflow_state.py (#1166).

Covers:
  - emit_state_transition(): append, dir creation, compact single-line JSON,
    fail-open on OSError / arbitrary exceptions, session_id join key.
  - derive_current_state() / compute_dwell_times(): pure replay over a
    session's transitions — current state is the last transition's
    new_state, dwell time is derived, never stored.
  - CLI `record` / `report` subcommands end-to-end.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_HOOKS_DIR = _PLUGIN_DIR / "hooks"
_LIB_DIR = _HOOKS_DIR / "lib"
_LIB_SCRIPT = _LIB_DIR / "workflow_state.py"
_TESTS_LIB = _PLUGIN_DIR / "tests" / "lib"

for _p in (_HOOKS_DIR, _LIB_DIR, _TESTS_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import workflow_state  # type: ignore[import-not-found]
from concurrency import (  # type: ignore[import-not-found]
    DEFAULT_DELAY_MS,
    DEFAULT_WORKERS,
)
from concurrency import (
    assert_concurrent_appends_produce_one_line_per_marker as _assert_concurrent_appends,
)
from jsonl import read_jsonl as _read_jsonl  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# emit_state_transition()
# ---------------------------------------------------------------------------


def test_emit_appends_one_compact_jsonl_line(tmp_path: Path) -> None:
    workflow_state.emit_state_transition(tmp_path, "ship", None, "SPEC")
    log = tmp_path / ".claude" / "metrics" / "workflow-states.jsonl"
    assert log.is_file()
    raw = log.read_text(encoding="utf-8")
    lines = raw.splitlines()
    assert len(lines) == 1
    assert raw.endswith("\n")
    assert ", " not in lines[0]
    assert '": ' not in lines[0]
    event = json.loads(lines[0])
    assert event["workflow"] == "ship"
    assert event["prior_state"] is None
    assert event["new_state"] == "SPEC"
    assert "ts" in event and "plugin_version" in event


def test_emit_creates_metrics_dir_when_absent(tmp_path: Path) -> None:
    assert not (tmp_path / ".claude" / "metrics").exists()
    workflow_state.emit_state_transition(tmp_path, "build", "SPEC", "PLAN")
    assert (tmp_path / ".claude" / "metrics").is_dir()


def test_emit_appends_not_overwrites_across_two_calls(tmp_path: Path) -> None:
    workflow_state.emit_state_transition(tmp_path, "ship", None, "SPEC")
    workflow_state.emit_state_transition(tmp_path, "ship", "SPEC", "PLAN")
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "workflow-states.jsonl")
    assert len(events) == 2
    assert events[0]["new_state"] == "SPEC"
    assert events[1]["new_state"] == "PLAN"


def test_emit_includes_session_id_when_given(tmp_path: Path) -> None:
    workflow_state.emit_state_transition(tmp_path, "ship", None, "SPEC", "sess-1")
    event = _read_jsonl(tmp_path / ".claude" / "metrics" / "workflow-states.jsonl")[0]
    assert event["session_id"] == "sess-1"


def test_emit_omits_session_id_when_absent(tmp_path: Path) -> None:
    workflow_state.emit_state_transition(tmp_path, "ship", None, "SPEC")
    event = _read_jsonl(tmp_path / ".claude" / "metrics" / "workflow-states.jsonl")[0]
    assert "session_id" not in event


def test_emit_fail_open_on_unwritable_metrics_dir(tmp_path: Path, monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(workflow_state.Path, "mkdir", _boom)
    # Must not raise.
    workflow_state.emit_state_transition(tmp_path, "ship", None, "SPEC")


# ---------------------------------------------------------------------------
# derive_current_state() / compute_dwell_times() — pure replay
# ---------------------------------------------------------------------------


def test_derive_current_state_is_last_transition() -> None:
    entries = [
        {"ts": "2026-01-01T00:00:00Z", "new_state": "SPEC"},
        {"ts": "2026-01-01T00:05:00Z", "new_state": "PLAN"},
        {"ts": "2026-01-01T00:10:00Z", "new_state": "BUILD"},
    ]
    assert workflow_state.derive_current_state(entries) == "BUILD"


def test_derive_current_state_empty_is_none() -> None:
    assert workflow_state.derive_current_state([]) is None


def test_compute_dwell_times_sums_gaps_between_transitions() -> None:
    entries = [
        {"ts": "2026-01-01T00:00:00Z", "new_state": "SPEC"},
        {"ts": "2026-01-01T00:05:00Z", "new_state": "PLAN"},
        {"ts": "2026-01-01T00:15:00Z", "new_state": "BUILD"},
    ]
    now = datetime(2026, 1, 1, 0, 20, 0, tzinfo=timezone.utc)
    dwell = workflow_state.compute_dwell_times(entries, now=now)
    assert dwell["SPEC"] == 300.0
    assert dwell["PLAN"] == 600.0
    assert dwell["BUILD"] == 300.0


def test_compute_dwell_times_accumulates_revisited_state() -> None:
    entries = [
        {"ts": "2026-01-01T00:00:00Z", "new_state": "REVIEW"},
        {"ts": "2026-01-01T00:02:00Z", "new_state": "BUILD"},
        {"ts": "2026-01-01T00:03:00Z", "new_state": "REVIEW"},
    ]
    now = datetime(2026, 1, 1, 0, 4, 0, tzinfo=timezone.utc)
    dwell = workflow_state.compute_dwell_times(entries, now=now)
    assert dwell["REVIEW"] == 120.0 + 60.0
    assert dwell["BUILD"] == 60.0


def test_compute_dwell_times_empty_is_empty_dict() -> None:
    assert workflow_state.compute_dwell_times([]) == {}


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------


def test_concurrent_emits_never_interleave_into_a_corrupted_line(tmp_path: Path) -> None:
    """#1889: N concurrent CLI `record` invocations must each land one intact
    JSONL line, never a torn/interleaved one.
    `DEV_TEAM_WORKFLOW_STATE_TEST_DELAY_MS` forces `atomic_state.append_line_locked`
    to split its write into two calls with a delay between them, simulating a
    genuinely non-atomic write so this is a deterministic regression guard
    (mirrors test_hook_state_concurrency.py, #1501). Each worker gets a
    distinct `--session` marker so a torn/interleaved merge that
    coincidentally still parses as JSON is still caught."""
    markers = [f"marker-{i}-end" for i in range(DEFAULT_WORKERS)]
    env = {**os.environ, "DEV_TEAM_WORKFLOW_STATE_TEST_DELAY_MS": str(DEFAULT_DELAY_MS)}
    cmds = [
        (
            [
                sys.executable,
                str(_LIB_SCRIPT),
                "record",
                "--cwd",
                str(tmp_path),
                "--workflow",
                "ship",
                "--new-state",
                "SPEC",
                "--session",
                marker,
            ],
            env,
        )
        for marker in markers
    ]
    log = tmp_path / ".claude" / "metrics" / "workflow-states.jsonl"
    _assert_concurrent_appends(cmds, log, markers)


def test_cli_record_then_report(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "record",
            "--cwd",
            str(tmp_path),
            "--workflow",
            "ship",
            "--new-state",
            "SPEC",
            "--session",
            "sess-1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "record",
            "--cwd",
            str(tmp_path),
            "--workflow",
            "ship",
            "--prior-state",
            "SPEC",
            "--new-state",
            "PLAN",
            "--session",
            "sess-1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "report",
            "--cwd",
            str(tmp_path),
            "--session",
            "sess-1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["current_state"] == "PLAN"
    assert report["transition_count"] == 2


def test_cli_report_filters_by_session(tmp_path: Path) -> None:
    workflow_state.emit_state_transition(tmp_path, "ship", None, "SPEC", "sess-a")
    workflow_state.emit_state_transition(tmp_path, "ship", None, "BUILD", "sess-b")
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "report",
            "--cwd",
            str(tmp_path),
            "--session",
            "sess-a",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["current_state"] == "SPEC"
    assert report["transition_count"] == 1
