"""Unit tests for hooks/destructive_guard.py (#732).

Covers the naming-cleanup fix for the compressed `_pat`/`proc`/`perm`
abbreviations in `main()`'s pattern-group unpacking.
"""

from __future__ import annotations

import inspect
import io
import json
import re
import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import destructive_guard  # type: ignore[import-not-found]  # noqa: E402


@pytest.fixture(autouse=True)
def _no_boundary_events(monkeypatch):
    """This suite calls destructive_guard.main() in-process with no `cwd`
    in the payload — without this, emit_boundary_event (#859) would resolve
    metrics/ against the test process's real OS cwd (the repo checkout).
    Boundary-event emission itself is covered end-to-end in
    tests/hooks/test_boundary_events.py.
    """
    monkeypatch.setattr(destructive_guard, "emit_boundary_event", lambda *a, **k: None)


def _feed(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))


def test_main_warns_on_process_destruction(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "kill -9 1234"}})
    assert destructive_guard.main() == 0
    out = capsys.readouterr().out
    assert (
        "CAUTION: Destructive command detected (Process destruction: kill -9)." in out
    )


def test_main_warns_on_permission_escalation(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "chmod 777 /etc/passwd"}})
    assert destructive_guard.main() == 0
    out = capsys.readouterr().out
    assert (
        "CAUTION: Destructive command detected (Permission escalation: chmod 777)."
        in out
    )


def test_main_silent_on_safe_allowlisted_command(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "rm -rf node_modules"}})
    assert destructive_guard.main() == 0
    assert capsys.readouterr().out == ""


def _no_probes(monkeypatch) -> None:
    """Force every context probe to resolve to a deterministic "no repo" state."""
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: None)
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: None)
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)


# --- Context probes (#862) --------------------------------------------------


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str) -> None:
        self.returncode = returncode
        self.stdout = stdout


def test_run_git_returns_stripped_stdout_on_success(monkeypatch):
    monkeypatch.setattr(
        destructive_guard.subprocess,
        "run",
        lambda *a, **k: _FakeCompleted(0, "main\n"),
    )
    assert destructive_guard._run_git(["rev-parse", "--abbrev-ref", "HEAD"]) == "main"


def test_run_git_returns_none_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(
        destructive_guard.subprocess, "run", lambda *a, **k: _FakeCompleted(128, "")
    )
    assert destructive_guard._run_git(["symbolic-ref", "--short", "x"]) is None


def test_run_git_returns_none_when_not_a_repo(monkeypatch):
    def _raise(*_a, **_k):
        raise destructive_guard.subprocess.SubprocessError("not a git repository")

    monkeypatch.setattr(destructive_guard.subprocess, "run", _raise)
    assert destructive_guard._run_git(["rev-parse", "--abbrev-ref", "HEAD"]) is None


def test_run_git_returns_none_on_timeout(monkeypatch):
    def _raise(*_a, **_k):
        raise destructive_guard.subprocess.TimeoutExpired(cmd="git", timeout=1.0)

    monkeypatch.setattr(destructive_guard.subprocess, "run", _raise)
    assert destructive_guard._run_git(["rev-parse", "--abbrev-ref", "HEAD"]) is None


def test_current_branch_returns_none_for_detached_head(monkeypatch):
    monkeypatch.setattr(destructive_guard, "_run_git", lambda args: "HEAD")
    assert destructive_guard._current_branch() is None


def test_default_branch_uses_symbolic_ref_when_available(monkeypatch):
    monkeypatch.setattr(
        destructive_guard,
        "_run_git",
        lambda args: "origin/main" if args[0] == "symbolic-ref" else None,
    )
    assert destructive_guard._default_branch() == "main"


def test_default_branch_falls_back_to_single_local_candidate(monkeypatch):
    def _fake(args):
        if args[0] == "symbolic-ref":
            return None
        if args == ["rev-parse", "--verify", "--quiet", "refs/heads/main"]:
            return "deadbeef"
        return None

    monkeypatch.setattr(destructive_guard, "_run_git", _fake)
    assert destructive_guard._default_branch() == "main"


def test_default_branch_unresolved_when_both_main_and_master_exist(monkeypatch):
    def _fake(args):
        if args[0] == "symbolic-ref":
            return None
        return "deadbeef"

    monkeypatch.setattr(destructive_guard, "_run_git", _fake)
    assert destructive_guard._default_branch() is None


def test_default_branch_unresolved_when_probes_fail(monkeypatch):
    monkeypatch.setattr(destructive_guard, "_run_git", lambda args: None)
    assert destructive_guard._default_branch() is None


def test_remote_url_delegates_to_run_git(monkeypatch):
    monkeypatch.setattr(
        destructive_guard,
        "_run_git",
        lambda args: "git@github.com:org/repo.git" if args[0] == "remote" else None,
    )
    assert destructive_guard._remote_url() == "git@github.com:org/repo.git"


def test_ci_active_true_when_env_set(monkeypatch):
    monkeypatch.setenv("CI", "true")
    assert destructive_guard._ci_active() is True


def test_ci_active_false_when_env_unset(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    assert destructive_guard._ci_active() is False


# --- Escalation paths (#862) -------------------------------------------------


def test_force_push_to_default_branch_blocks_without_careful_mode(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "git push --force origin main"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)
    monkeypatch.delenv(destructive_guard._OVERRIDE_ENV_VAR, raising=False)

    assert destructive_guard.main() == 2
    out = capsys.readouterr().out
    assert "BLOCKED" in out
    assert "default branch" in out
    assert "careful mode" not in out.lower() or "regardless of careful mode" in out.lower()
    assert "/careful off" not in out


def test_bare_force_push_escalates_when_head_is_default_branch(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "git push --force"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)
    monkeypatch.delenv(destructive_guard._OVERRIDE_ENV_VAR, raising=False)

    assert destructive_guard.main() == 2
    assert "BLOCKED" in capsys.readouterr().out


def test_force_push_on_feature_branch_keeps_warn_behavior(monkeypatch, capsys):
    _feed(
        monkeypatch, {"tool_input": {"command": "git push --force origin feature/x"}}
    )
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "feature/x")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)

    assert destructive_guard.main() == 0
    out = capsys.readouterr().out
    assert (
        "CAUTION: Destructive command detected (Git destruction: git push --force)."
        in out
    )


def test_branch_delete_of_default_branch_blocks_regardless_of_current_branch(
    monkeypatch, capsys
):
    _feed(monkeypatch, {"tool_input": {"command": "git branch -D main"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "feature/other")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)

    assert destructive_guard.main() == 2
    assert "BLOCKED" in capsys.readouterr().out


def test_reset_hard_escalates_only_when_head_is_default_branch(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "git reset --hard"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)

    assert destructive_guard.main() == 2
    assert "BLOCKED" in capsys.readouterr().out


def test_reset_hard_warns_on_feature_branch(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "git reset --hard"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "feature/x")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)

    assert destructive_guard.main() == 0
    out = capsys.readouterr().out
    assert (
        "CAUTION: Destructive command detected (Git destruction: git reset --hard)."
        in out
    )


def test_guard_degrades_outside_git_repo_or_on_git_failure(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "git push --force origin main"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    _no_probes(monkeypatch)

    assert destructive_guard.main() == 0
    out = capsys.readouterr().out
    assert "CAUTION" in out


def test_json_without_escalations_key_is_byte_compatible(monkeypatch, capsys, tmp_path):
    config = {
        "file_destruction": ["rm -rf"],
        "database_destruction": ["drop table"],
        "git_destruction": ["git push --force"],
        "process_destruction": ["kill -9"],
        "permission_escalation": ["chmod 777"],
        "safe_allowlist": [],
    }
    config_path = tmp_path / "destructive-commands.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(destructive_guard, "_COMMANDS_FILE", config_path)
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    _feed(monkeypatch, {"tool_input": {"command": "git push --force origin main"}})

    assert destructive_guard.main() == 0
    out = capsys.readouterr().out
    assert (
        "CAUTION: Destructive command detected (Git destruction: git push --force)."
        in out
    )
    assert "BLOCKED" not in out


def test_careful_mode_block_still_covers_everything_escalation_or_not(
    monkeypatch, capsys
):
    _feed(monkeypatch, {"tool_input": {"command": "git push --force origin feature/x"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: True)

    assert destructive_guard.main() == 2
    out = capsys.readouterr().out
    assert "Careful mode is active" in out
    assert "/careful off" in out


def test_one_shot_override_bypasses_escalation(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "git push --force origin main"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)
    monkeypatch.setenv(destructive_guard._OVERRIDE_ENV_VAR, "1")

    assert destructive_guard.main() == 0
    out = capsys.readouterr().out
    assert "CAUTION" in out
    assert "BLOCKED" not in out


def test_decision_logged_when_boundary_events_channel_exists(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "git push --force origin main"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)

    events = []

    def _fake_emit(cwd, hook, tool, decision, matched_rule, session_id=None):
        events.append(
            {
                "hook": hook,
                "tool": tool,
                "decision": decision,
                "matched_rule": matched_rule,
            }
        )

    monkeypatch.setattr(destructive_guard, "emit_boundary_event", _fake_emit)

    assert destructive_guard.main() == 2
    assert len(events) == 1
    assert events[0]["hook"] == "destructive_guard"
    assert events[0]["tool"] == "Bash"
    assert events[0]["decision"] == "block"
    assert events[0]["matched_rule"] == "git push --force"


def test_escalation_override_emits_bypass_decision(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "git push --force origin main"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)
    monkeypatch.setenv(destructive_guard._OVERRIDE_ENV_VAR, "1")

    events = []
    monkeypatch.setattr(
        destructive_guard,
        "emit_boundary_event",
        lambda cwd, hook, tool, decision, matched_rule, session_id=None: events.append(
            decision
        ),
    )

    assert destructive_guard.main() == 0
    assert events == ["bypass"]


def test_non_escalating_match_emits_exactly_one_warn_event(monkeypatch, capsys):
    # A matched pattern that carries an escalation rule but doesn't escalate
    # (feature branch, not default) must not double-log: one "warn" event,
    # not one from the escalation path and one from the plain warn path.
    _feed(monkeypatch, {"tool_input": {"command": "git push --force origin feature/x"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "feature/x")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)

    events = []
    monkeypatch.setattr(
        destructive_guard,
        "emit_boundary_event",
        lambda cwd, hook, tool, decision, matched_rule, session_id=None: events.append(
            decision
        ),
    )

    assert destructive_guard.main() == 0
    assert events == ["warn"]


def test_boundary_events_channel_absent_does_not_raise_or_print(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": "git push --force origin main"}})
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_remote_url", lambda: None)
    monkeypatch.setattr(destructive_guard, "_ci_active", lambda: False)

    # Simulate the #859 channel misbehaving (e.g. unwritable metrics/) —
    # the local safety-net wrapper must swallow it silently either way.
    def _raise(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(destructive_guard, "_emit_boundary_event", _raise)

    assert destructive_guard.main() == 2
    out = capsys.readouterr().out
    assert "BLOCKED" in out


def test_main_uses_descriptive_pattern_group_names():
    # Low-severity naming finding (#732): `main()` unpacked pattern groups
    # into compressed abbreviations (`proc_pat`, `perm_pat`, etc.). These
    # should carry full descriptive names.
    source = inspect.getsource(destructive_guard.main)
    for cryptic in (
        "file_pat",
        "db_pat",
        "git_pat",
        "proc_pat",
        "perm_pat",
        "safe_pat",
    ):
        assert re.search(rf"\b{cryptic}\b", source) is None
    for descriptive in (
        "file_patterns",
        "database_patterns",
        "git_patterns",
        "process_patterns",
        "permission_patterns",
        "safe_patterns",
    ):
        assert descriptive in source
