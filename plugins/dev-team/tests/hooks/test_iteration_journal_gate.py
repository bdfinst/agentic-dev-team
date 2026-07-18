"""Unit tests for hooks/lib/iteration_journal_gate.py (#1168).

Covers:
  - record_iteration_entry(): append, dir creation, compact single-line
    JSON, fail-open on OSError / arbitrary exceptions, session_id join key.
  - check_iteration_journal(): blocks when no entry exists for round_id,
    allows when a matching entry exists.
  - CLI `record` / `check` subcommands end-to-end, including the exit-code
    contract (0 allowed, 1 blocked) and the boundary event emitted on block.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_HOOKS_DIR = _PLUGIN_DIR / "hooks"
_LIB_DIR = _HOOKS_DIR / "lib"
_LIB_SCRIPT = _LIB_DIR / "iteration_journal_gate.py"

for _p in (_HOOKS_DIR, _LIB_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import iteration_journal_gate  # type: ignore[import-not-found]  # noqa: E402


def _read_jsonl(path: Path) -> list:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


# ---------------------------------------------------------------------------
# record_iteration_entry()
# ---------------------------------------------------------------------------


def test_record_appends_one_compact_jsonl_line(tmp_path: Path) -> None:
    iteration_journal_gate.record_iteration_entry(
        tmp_path, "round-1", "ran tests", "green", "next issue"
    )
    log = tmp_path / "metrics" / "iteration-journal.jsonl"
    assert log.is_file()
    raw = log.read_text(encoding="utf-8")
    lines = raw.splitlines()
    assert len(lines) == 1
    assert raw.endswith("\n")
    assert ", " not in lines[0]
    assert '": ' not in lines[0]
    entry = json.loads(lines[0])
    assert entry["round_id"] == "round-1"
    assert entry["attempted"] == "ran tests"
    assert entry["outcome"] == "green"
    assert entry["next_action"] == "next issue"
    assert "ts" in entry and "plugin_version" in entry


def test_record_creates_metrics_dir_when_absent(tmp_path: Path) -> None:
    assert not (tmp_path / "metrics").exists()
    iteration_journal_gate.record_iteration_entry(
        tmp_path, "round-1", "a", "b", "c"
    )
    assert (tmp_path / "metrics").is_dir()


def test_record_appends_not_overwrites_across_two_calls(tmp_path: Path) -> None:
    iteration_journal_gate.record_iteration_entry(tmp_path, "round-1", "a", "b", "c")
    iteration_journal_gate.record_iteration_entry(tmp_path, "round-2", "d", "e", "f")
    entries = _read_jsonl(tmp_path / "metrics" / "iteration-journal.jsonl")
    assert len(entries) == 2
    assert entries[0]["round_id"] == "round-1"
    assert entries[1]["round_id"] == "round-2"


def test_record_includes_session_id_when_given(tmp_path: Path) -> None:
    iteration_journal_gate.record_iteration_entry(
        tmp_path, "round-1", "a", "b", "c", session_id="sess-1"
    )
    entry = _read_jsonl(tmp_path / "metrics" / "iteration-journal.jsonl")[0]
    assert entry["session_id"] == "sess-1"


def test_record_omits_session_id_when_absent(tmp_path: Path) -> None:
    iteration_journal_gate.record_iteration_entry(tmp_path, "round-1", "a", "b", "c")
    entry = _read_jsonl(tmp_path / "metrics" / "iteration-journal.jsonl")[0]
    assert "session_id" not in entry


def test_record_fails_open_on_unwritable_metrics_dir(
    tmp_path: Path, monkeypatch
) -> None:
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(iteration_journal_gate.Path, "mkdir", _boom)
    # Must not raise.
    iteration_journal_gate.record_iteration_entry(tmp_path, "round-1", "a", "b", "c")


def test_record_fails_open_on_arbitrary_exception(tmp_path: Path, monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise RuntimeError("disk is on fire")

    monkeypatch.setattr(iteration_journal_gate, "_isoformat_utc", _boom)
    # Must not raise.
    iteration_journal_gate.record_iteration_entry(tmp_path, "round-1", "a", "b", "c")
    assert not (tmp_path / "metrics" / "iteration-journal.jsonl").exists()


# ---------------------------------------------------------------------------
# check_iteration_journal()
# ---------------------------------------------------------------------------


def test_check_blocks_when_no_matching_entry(tmp_path: Path) -> None:
    allowed, reason = iteration_journal_gate.check_iteration_journal(
        "round-1", cwd=tmp_path
    )
    assert allowed is False
    assert reason == "iteration-journal-missing"


def test_check_allows_when_matching_entry_exists(tmp_path: Path) -> None:
    iteration_journal_gate.record_iteration_entry(tmp_path, "round-1", "a", "b", "c")
    allowed, reason = iteration_journal_gate.check_iteration_journal(
        "round-1", cwd=tmp_path
    )
    assert allowed is True
    assert reason == "ok"


def test_check_does_not_match_a_different_round_id(tmp_path: Path) -> None:
    iteration_journal_gate.record_iteration_entry(tmp_path, "round-1", "a", "b", "c")
    allowed, _ = iteration_journal_gate.check_iteration_journal(
        "round-2", cwd=tmp_path
    )
    assert allowed is False


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------


def test_cli_check_blocks_and_emits_boundary_event(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "check",
            "--cwd",
            str(tmp_path),
            "--round-id",
            "round-1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["allowed"] is False
    events = _read_jsonl(tmp_path / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    assert events[0]["hook"] == "iteration_journal_gate"
    assert events[0]["tool"] == "Skill"
    assert events[0]["decision"] == "block"
    assert events[0]["matched_rule"] == "iteration-journal-missing"


def test_cli_record_then_check_allows(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "record",
            "--cwd",
            str(tmp_path),
            "--round-id",
            "round-1",
            "--attempted",
            "ran build",
            "--outcome",
            "green",
            "--next-action",
            "advance",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_SCRIPT),
            "check",
            "--cwd",
            str(tmp_path),
            "--round-id",
            "round-1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["allowed"] is True
    assert not (tmp_path / "metrics" / "boundary-events.jsonl").exists()
