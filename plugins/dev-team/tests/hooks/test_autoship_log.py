"""Unit tests for hooks/lib/autoship_log.py.

Covers:
  - append_round(): append, dir creation, adds `logged_at`.
  - CLI `--json` / `--json-file` sources, invalid-JSON / non-dict rejection.
  - concurrency (#1889): N concurrent appends never interleave into a
    corrupted line.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_HOOKS_DIR = _PLUGIN_DIR / "hooks"
_LIB_DIR = _HOOKS_DIR / "lib"
_LIB_SCRIPT = _LIB_DIR / "autoship_log.py"
_TESTS_LIB = _PLUGIN_DIR / "tests" / "lib"

for _p in (_HOOKS_DIR, _LIB_DIR, _TESTS_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import autoship_log  # type: ignore[import-not-found]
from concurrency import (  # type: ignore[import-not-found]
    DEFAULT_DELAY_MS,
    DEFAULT_WORKERS,
)
from concurrency import (
    assert_concurrent_appends_produce_one_line_per_marker as _assert_concurrent_appends,
)
from jsonl import read_jsonl as _read_jsonl  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# append_round()
# ---------------------------------------------------------------------------


def test_append_round_appends_one_compact_jsonl_line(tmp_path: Path) -> None:
    log = tmp_path / "round-log.jsonl"
    autoship_log.append_round(str(log), {"issue": "#1", "outcome": "shipped"})
    entries = _read_jsonl(log)
    assert len(entries) == 1
    assert entries[0]["issue"] == "#1"
    assert entries[0]["outcome"] == "shipped"
    assert "logged_at" in entries[0]


def test_append_round_creates_parent_dir_when_absent(tmp_path: Path) -> None:
    log = tmp_path / "nested" / "round-log.jsonl"
    autoship_log.append_round(str(log), {"issue": "#2"})
    assert log.is_file()


def test_append_round_appends_not_overwrites_across_two_calls(tmp_path: Path) -> None:
    log = tmp_path / "round-log.jsonl"
    autoship_log.append_round(str(log), {"issue": "#1"})
    autoship_log.append_round(str(log), {"issue": "#2"})
    entries = _read_jsonl(log)
    assert [e["issue"] for e in entries] == ["#1", "#2"]


def test_append_round_propagates_oserror_from_a_failed_write(tmp_path: Path) -> None:
    """Unlike its fail-open siblings (boundary_events.py, workflow_state.py,
    iteration_journal_gate.py), append_round() must NOT swallow a write
    failure — the /autoship round-log caller needs to know the round wasn't
    actually recorded, not silently proceed as if it were. Uses a real OSError
    (log path names an existing directory, so open("a") raises
    IsADirectoryError) rather than monkeypatching, since append_round now
    delegates to atomic_state.append_line_locked, which opens the file via
    the builtin open() rather than Path.open()."""
    log_dir = tmp_path / "round-log-is-a-dir"
    log_dir.mkdir()
    with pytest.raises(OSError):
        autoship_log.append_round(str(log_dir), {"issue": "#1"})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_json_arg_appends_one_entry(tmp_path: Path) -> None:
    log = tmp_path / "round-log.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "--log-path",
            str(log),
            "--json",
            json.dumps({"issue": "#3"}),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    entries = _read_jsonl(log)
    assert entries[0]["issue"] == "#3"


def test_cli_json_file_arg_appends_one_entry(tmp_path: Path) -> None:
    log = tmp_path / "round-log.jsonl"
    json_file = tmp_path / "payload.json"
    json_file.write_text(json.dumps({"issue": "#4"}), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "--log-path",
            str(log),
            "--json-file",
            str(json_file),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    entries = _read_jsonl(log)
    assert entries[0]["issue"] == "#4"


def test_cli_rejects_invalid_json(tmp_path: Path) -> None:
    log = tmp_path / "round-log.jsonl"
    result = subprocess.run(
        [sys.executable, str(_LIB_SCRIPT), "--log-path", str(log), "--json", "not json"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode != 0
    assert not log.exists()


def test_cli_rejects_non_dict_json(tmp_path: Path) -> None:
    log = tmp_path / "round-log.jsonl"
    result = subprocess.run(
        [sys.executable, str(_LIB_SCRIPT), "--log-path", str(log), "--json", "[1, 2]"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode != 0
    assert not log.exists()


def test_cli_write_failure_crashes_rather_than_swallowing(tmp_path: Path) -> None:
    """A write failure (here: --log-path names an existing directory, so
    `path.open("a")` raises IsADirectoryError) must surface as a crash, not
    the graceful `return 1` the CLI uses for a bad --json payload — matching
    append_round()'s not-fail-open contract. main() has no try/except around
    the append_round() call, so this asserts the CLI actually keeps that gap
    open rather than accidentally starting to swallow it."""
    log_dir = tmp_path / "round-log-is-a-dir"
    log_dir.mkdir()
    result = subprocess.run(
        [sys.executable, str(_LIB_SCRIPT), "--log-path", str(log_dir), "--json", "{}"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode != 0
    assert "IsADirectoryError" in result.stderr or "OSError" in result.stderr


# ---------------------------------------------------------------------------
# concurrency (#1889)
# ---------------------------------------------------------------------------


def test_concurrent_appends_never_interleave_into_a_corrupted_line(tmp_path: Path) -> None:
    """N concurrent CLI invocations must each land one intact JSONL line,
    never a torn/interleaved one. `DEV_TEAM_AUTOSHIP_LOG_TEST_DELAY_MS`
    forces the write to split into two calls with a delay between them,
    simulating a genuinely non-atomic write so this is a deterministic
    regression guard (mirrors test_hook_state_concurrency.py, #1501). Each
    worker gets a distinct `issue` marker so a torn/interleaved merge that
    coincidentally still parses as JSON is still caught."""
    markers = [f"marker-{i}-end" for i in range(DEFAULT_WORKERS)]
    log = tmp_path / "round-log.jsonl"
    env = {**os.environ, "DEV_TEAM_AUTOSHIP_LOG_TEST_DELAY_MS": str(DEFAULT_DELAY_MS)}
    cmds = [
        (
            [
                sys.executable,
                str(_LIB_SCRIPT),
                "--log-path",
                str(log),
                "--json",
                json.dumps({"issue": marker}),
            ],
            env,
        )
        for marker in markers
    ]
    _assert_concurrent_appends(cmds, log, markers)
