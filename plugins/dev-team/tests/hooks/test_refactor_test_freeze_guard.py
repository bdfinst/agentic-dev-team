"""Unit tests for hooks/refactor_test_freeze_guard.py (#813).

Block, pass-through, staleness, and fail-open paths of the PreToolUse half
of the tests-frozen-during-refactor enforcement.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

import refactor_test_freeze_guard as guard
from test_file_classify import STALE_AFTER_SECONDS

_WRITTEN_AT = "2026-07-04T10:00:00+00:00"
_WRITTEN_AT_EPOCH = 1783159200.0


def _write_state(tmp_path: Path, phase: str = "refactor", **overrides) -> None:
    state = {
        "phase": phase,
        "step": "2.1",
        "written_at": _WRITTEN_AT,
        "test_files_staged": [],
    }
    state.update(overrides)
    path = tmp_path / "memory" / "build-phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def _audit_events(tmp_path: Path):
    path = tmp_path / ".claude" / "metrics" / "refactor-freeze.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


_NOW = _WRITTEN_AT_EPOCH + 60


def test_test_file_edit_is_blocked_during_refactor(tmp_path):
    _write_state(tmp_path)
    code, lines = guard.evaluate("src/thing.test.ts", tmp_path, now=_NOW)
    assert code == 2
    assert lines[0].startswith("[BLOCK]")


def test_denial_names_the_invariant_and_the_recovery_path(tmp_path):
    _write_state(tmp_path)
    _, lines = guard.evaluate("src/thing.test.ts", tmp_path, now=_NOW)
    body = " ".join(lines)
    assert "never change a test" in body
    assert "TEST phase" in body and "re-enter REFACTOR" in body


def test_block_is_recorded_in_the_audit_log(tmp_path):
    _write_state(tmp_path)
    guard.evaluate("src/thing.test.ts", tmp_path, now=_NOW)
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["block"]
    assert events[0]["file"] == "src/thing.test.ts"
    assert events[0]["step"] == "2.1"


def test_production_file_edit_is_allowed_during_refactor(tmp_path):
    _write_state(tmp_path)
    code, lines = guard.evaluate("src/thing.ts", tmp_path, now=_NOW)
    assert (code, lines) == (0, [])


def test_test_file_edit_is_allowed_when_no_phase_is_recorded(tmp_path):
    code, lines = guard.evaluate("src/thing.test.ts", tmp_path, now=_NOW)
    assert (code, lines) == (0, [])


def test_test_file_edit_is_allowed_during_implement_and_test_phases(tmp_path):
    for phase in ("implement", "test", "red", "green"):
        _write_state(tmp_path, phase=phase)
        code, lines = guard.evaluate("src/thing.test.ts", tmp_path, now=_NOW)
        assert (code, lines) == (0, []), phase


def test_stale_refactor_state_does_not_linger(tmp_path):
    _write_state(tmp_path)
    code, lines = guard.evaluate(
        "src/thing.test.ts", tmp_path, now=_WRITTEN_AT_EPOCH + STALE_AFTER_SECONDS + 1
    )
    assert (code, lines) == (0, [])


def test_malformed_state_fails_open_with_an_audit_line(tmp_path):
    path = tmp_path / "memory" / "build-phase.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    code, lines = guard.evaluate("src/thing.test.ts", tmp_path, now=_NOW)
    assert (code, lines) == (0, [])
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["fail-open"]


def test_empty_file_path_passes_silently(tmp_path):
    _write_state(tmp_path)
    assert guard.evaluate("", tmp_path, now=_NOW) == (0, [])


def test_main_fails_open_on_internal_error(tmp_path, monkeypatch, capsys):
    """A crash inside the guard never blocks the tool call."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        guard, "read_stdin_json", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert guard.main() == 0
    assert capsys.readouterr().out == ""
    events = _audit_events(tmp_path)
    assert [e["event"] for e in events] == ["fail-open"]


def test_main_blocks_via_stdin_payload(tmp_path, monkeypatch, capsys):
    _write_state(tmp_path, written_at=None)
    # fresh written_at so main()'s real clock sees an active phase
    import datetime

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _write_state(tmp_path, written_at=now_iso)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        guard,
        "read_stdin_json",
        lambda: {"tool_input": {"file_path": "src/thing.spec.ts"}},
    )
    assert guard.main() == 2
    assert "[BLOCK]" in capsys.readouterr().out


def test_project_dir_ignores_stale_claude_project_dir_env_var(
    tmp_path, monkeypatch
) -> None:
    """CLAUDE_PROJECT_DIR is no longer read at all — a stale/unset value must
    never override git-root resolution."""
    stale = tmp_path / "stale-elsewhere"
    stale.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(stale))
    monkeypatch.chdir(tmp_path)
    assert guard._project_dir() == tmp_path
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    assert guard._project_dir() == tmp_path
