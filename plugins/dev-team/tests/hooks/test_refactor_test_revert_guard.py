"""Unit tests for hooks/refactor_test_revert_guard.py (#813).

Baseline carryover, post-baseline revert, untracked-file removal,
pass-through, and fail-open paths of the PostToolUse (Bash) half of the
tests-frozen-during-refactor enforcement, against a real git fixture.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

import refactor_test_revert_guard as guard

_WRITTEN_AT = "2026-07-04T10:00:00+00:00"
_WRITTEN_AT_EPOCH = 1783159200.0
_NOW = _WRITTEN_AT_EPOCH + 60

_BASELINE_CONTENT = "test('carried over from TEST phase', () => {});\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "thing.js").write_text("export const x = 1;\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    # TEST phase edits the step's test file; the TEST->REFACTOR transition
    # stages it — the index is the refactor baseline.
    (tmp_path / "src" / "thing.test.js").write_text(_BASELINE_CONTENT)
    _git(tmp_path, "add", "src/thing.test.js")
    return tmp_path


def _write_state(repo: Path, phase: str = "refactor", **overrides) -> None:
    state = {
        "phase": phase,
        "step": "1.2",
        "written_at": _WRITTEN_AT,
        "test_files_staged": ["src/thing.test.js"],
    }
    state.update(overrides)
    path = repo / "memory" / "build-phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def _audit_events(repo: Path):
    path = repo / "metrics" / "refactor-freeze.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _boundary_events(repo: Path):
    path = repo / "metrics" / "boundary-events.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_baseline_carryover_is_never_reverted(repo):
    _write_state(repo)
    code, lines = guard.evaluate(repo, now=_NOW)
    assert code == 0
    assert lines == []
    assert (repo / "src" / "thing.test.js").read_text() == _BASELINE_CONTENT
    assert [e for e in _audit_events(repo) if e["event"] == "revert"] == []


def test_post_baseline_change_is_restored_with_advisory_and_audit(repo):
    _write_state(repo)
    (repo / "src" / "thing.test.js").write_text("test('weakened', () => {});\n")
    code, lines = guard.evaluate(repo, now=_NOW)
    assert code == 0
    assert (repo / "src" / "thing.test.js").read_text() == _BASELINE_CONTENT
    assert any(line.startswith("ADVISORY:") for line in lines)
    assert any("TEST" in line and "REFACTOR" in line for line in lines)
    events = _audit_events(repo)
    assert [e["event"] for e in events] == ["revert"]
    assert events[0]["file"] == "src/thing.test.js"


def test_post_baseline_restore_emits_a_revert_boundary_event(repo):
    """#906: restoring a dirtied baseline test file emits one boundary
    event with decision "revert" and matched_rule "restore-baseline"."""
    _write_state(repo)
    (repo / "src" / "thing.test.js").write_text("test('weakened', () => {});\n")
    guard.evaluate(repo, now=_NOW, session_id="sess-1")
    events = _boundary_events(repo)
    assert len(events) == 1
    assert events[0]["decision"] == "revert"
    assert events[0]["hook"] == "refactor_test_revert_guard"
    assert events[0]["tool"] == "Bash"
    assert events[0]["matched_rule"] == "restore-baseline"
    assert events[0]["session_id"] == "sess-1"


def test_deleted_baseline_test_file_is_restored(repo):
    _write_state(repo)
    (repo / "src" / "thing.test.js").unlink()
    guard.evaluate(repo, now=_NOW)
    assert (repo / "src" / "thing.test.js").read_text() == _BASELINE_CONTENT


def test_test_file_created_during_refactor_is_removed(repo):
    _write_state(repo)
    rogue = repo / "src" / "rogue.spec.js"
    rogue.write_text("test('unreviewed', () => {});\n")
    code, lines = guard.evaluate(repo, now=_NOW)
    assert code == 0
    assert not rogue.exists()
    assert any("removed" in line for line in lines)
    events = _audit_events(repo)
    assert [e["event"] for e in events] == ["remove"]
    assert events[0]["file"] == "src/rogue.spec.js"


def test_new_test_file_removal_emits_a_revert_boundary_event(repo):
    """#906: removing an untracked test file created during REFACTOR emits
    one boundary event with decision "revert" and matched_rule
    "remove-untracked-test"."""
    _write_state(repo)
    rogue = repo / "src" / "rogue.spec.js"
    rogue.write_text("test('unreviewed', () => {});\n")
    guard.evaluate(repo, now=_NOW, session_id="sess-2")
    events = _boundary_events(repo)
    assert len(events) == 1
    assert events[0]["decision"] == "revert"
    assert events[0]["hook"] == "refactor_test_revert_guard"
    assert events[0]["matched_rule"] == "remove-untracked-test"
    assert events[0]["session_id"] == "sess-2"


def test_boundary_event_channel_absence_degrades_silently(repo, monkeypatch):
    """Soft dependency on #859/PR #887 (attempt-and-degrade, same pattern
    #862 uses): even if the boundary-events channel raises internally, the
    revert guard's own behavior, stdout, and exit code are unaffected."""
    _write_state(repo)
    (repo / "src" / "thing.test.js").write_text("test('weakened', () => {});\n")
    monkeypatch.setattr(
        guard, "_emit_boundary_event", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    code, lines = guard.evaluate(repo, now=_NOW)
    assert code == 0
    assert (repo / "src" / "thing.test.js").read_text() == _BASELINE_CONTENT
    assert any(line.startswith("ADVISORY:") for line in lines)


def test_untracked_non_test_file_is_left_alone(repo):
    _write_state(repo)
    scratch = repo / "src" / "scratch.js"
    scratch.write_text("export const y = 2;\n")
    code, lines = guard.evaluate(repo, now=_NOW)
    assert (code, lines) == (0, [])
    assert scratch.exists()


def test_no_op_outside_a_refactor_phase(repo):
    _write_state(repo, phase="test")
    (repo / "src" / "thing.test.js").write_text("test('mid-TEST edit', () => {});\n")
    code, lines = guard.evaluate(repo, now=_NOW)
    assert (code, lines) == (0, [])
    assert "mid-TEST edit" in (repo / "src" / "thing.test.js").read_text()


def test_no_op_when_no_state_is_recorded(repo):
    (repo / "src" / "thing.test.js").write_text("dirty\n")
    code, lines = guard.evaluate(repo, now=_NOW)
    assert (code, lines) == (0, [])
    assert (repo / "src" / "thing.test.js").read_text() == "dirty\n"


def test_malformed_state_fails_open_without_reverting(repo):
    path = repo / "memory" / "build-phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    (repo / "src" / "thing.test.js").write_text("dirty\n")
    code, lines = guard.evaluate(repo, now=_NOW)
    assert (code, lines) == (0, [])
    assert (repo / "src" / "thing.test.js").read_text() == "dirty\n"
    events = _audit_events(repo)
    assert [e["event"] for e in events] == ["fail-open"]


def test_git_failure_fails_open_without_reverting(repo, monkeypatch):
    _write_state(repo)
    (repo / "src" / "thing.test.js").write_text("dirty\n")
    monkeypatch.setattr(guard, "_git", lambda *_args, **_kw: None)
    code, lines = guard.evaluate(repo, now=_NOW)
    assert (code, lines) == (0, [])
    assert (repo / "src" / "thing.test.js").read_text() == "dirty\n"
    events = _audit_events(repo)
    assert events and all(e["event"] == "fail-open" for e in events)


def test_stale_refactor_state_is_a_no_op(repo):
    from test_file_classify import STALE_AFTER_SECONDS

    _write_state(repo)
    (repo / "src" / "thing.test.js").write_text("dirty\n")
    code, lines = guard.evaluate(
        repo, now=_WRITTEN_AT_EPOCH + STALE_AFTER_SECONDS + 1
    )
    assert (code, lines) == (0, [])
    assert (repo / "src" / "thing.test.js").read_text() == "dirty\n"


def test_main_fails_open_on_internal_error(repo, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    monkeypatch.setattr(
        guard, "evaluate", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    monkeypatch.setattr(guard.sys, "stdin", __import__("io").StringIO("{}"))
    assert guard.main() == 0
    assert capsys.readouterr().out == ""
    events = _audit_events(repo)
    assert [e["event"] for e in events] == ["fail-open"]
