"""Unit tests for hooks/session_learning_trigger.py (#603).

Behavioural coverage of the state file helpers and `main()` decision paths.
Parity vs bash lives in `tests/hooks/parity/test_session_learning_trigger_parity.py`.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))

import session_learning_trigger as slt  # noqa: E402


# ---------------------------------------------------------------------------
# _load_counter
# ---------------------------------------------------------------------------


def test_load_counter_absent_returns_zero(tmp_path):
    assert slt._load_counter(tmp_path / "missing.json") == 0


def test_load_counter_reads_int(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"counter":7}')
    assert slt._load_counter(p) == 7


def test_load_counter_recovers_from_corrupt_json(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("this is not json")
    assert slt._load_counter(p) == 0


def test_load_counter_recovers_from_non_integer(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"counter":"seven"}')
    assert slt._load_counter(p) == 0


def test_load_counter_accepts_numeric_string(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"counter":"3"}')
    assert slt._load_counter(p) == 3


# ---------------------------------------------------------------------------
# _write_state
# ---------------------------------------------------------------------------


def test_write_state_writes_json_atomically(tmp_path):
    state = tmp_path / "metrics" / "learning-loop-state.json"
    slt._write_state(state, 5)
    assert state.read_text().rstrip() == '{"counter":5}'


def test_write_state_trailing_newline_matches_bash(tmp_path):
    state = tmp_path / "metrics" / "learning-loop-state.json"
    slt._write_state(state, 1)
    assert state.read_text().endswith("\n")


def test_write_state_leaves_no_temp_files_on_success(tmp_path):
    state = tmp_path / "metrics" / "learning-loop-state.json"
    slt._write_state(state, 2)
    leftovers = list(state.parent.glob(".learning-loop-state-*"))
    assert leftovers == []


# ---------------------------------------------------------------------------
# shell_quote — used to build the fire-and-forget subprocess command
# ---------------------------------------------------------------------------


def test_shell_quote_wraps_and_escapes():
    assert slt.shell_quote("plain") == "'plain'"
    assert slt.shell_quote("has'quote") == "'has'\"'\"'quote'"


# ---------------------------------------------------------------------------
# main() decision paths — mock the dispatch so we don't fork a child
# ---------------------------------------------------------------------------


def _feed_stdin(monkeypatch, text):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_main_consent_off_exits_zero(monkeypatch, tmp_path):
    monkeypatch.delenv("DEV_TEAM_AUTO_REVIEW", raising=False)
    _feed_stdin(monkeypatch, '{"cwd":"' + str(tmp_path) + '"}')
    assert slt.main() == 0
    assert not (tmp_path / "metrics" / "learning-loop-state.json").exists()


def test_main_malformed_json_exits_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
    _feed_stdin(monkeypatch, "not-json")
    assert slt.main() == 0
    # No state file created since parse failed early.
    assert not (tmp_path / "metrics" / "learning-loop-state.json").exists()


def test_main_increments_counter(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW_THRESHOLD", "5")
    monkeypatch.chdir(tmp_path)
    _feed_stdin(monkeypatch, '{"cwd":"' + str(tmp_path) + '","session_id":"s1"}')
    # Prevent actual background dispatch attempt (irrelevant for counter step).
    monkeypatch.setattr(slt, "_dispatch_background_analysis", lambda *_a, **_k: None)
    assert slt.main() == 0
    state = tmp_path / "metrics" / "learning-loop-state.json"
    assert json.loads(state.read_text()) == {"counter": 1}


def test_main_dispatches_and_resets_counter_at_threshold(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW_THRESHOLD", "2")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "metrics").mkdir()
    (tmp_path / "metrics" / "learning-loop-state.json").write_text('{"counter":1}')

    dispatched = []

    def fake_dispatch(cwd, session_id, hook_dir):
        dispatched.append((str(cwd), session_id, str(hook_dir)))

    monkeypatch.setattr(slt, "_dispatch_background_analysis", fake_dispatch)
    _feed_stdin(monkeypatch, '{"cwd":"' + str(tmp_path) + '","session_id":"sX"}')

    assert slt.main() == 0
    assert dispatched, "dispatch should fire at threshold"
    state = tmp_path / "metrics" / "learning-loop-state.json"
    # Counter reset to 0 after dispatch
    assert json.loads(state.read_text()) == {"counter": 0}


def test_main_falls_back_to_pwd_when_cwd_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(slt, "_dispatch_background_analysis", lambda *_a, **_k: None)
    _feed_stdin(monkeypatch, "{}")
    assert slt.main() == 0
    # State file created under PWD.
    state = tmp_path / "metrics" / "learning-loop-state.json"
    assert state.exists()


def test_main_invalid_threshold_env_uses_default(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW", "on")
    monkeypatch.setenv("DEV_TEAM_AUTO_REVIEW_THRESHOLD", "not-a-number")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(slt, "_dispatch_background_analysis", lambda *_a, **_k: None)
    _feed_stdin(monkeypatch, '{"cwd":"' + str(tmp_path) + '"}')
    assert slt.main() == 0
    # With default threshold=5, counter=1 after first invocation.
    state = tmp_path / "metrics" / "learning-loop-state.json"
    assert json.loads(state.read_text()) == {"counter": 1}
