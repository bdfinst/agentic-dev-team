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

import destructive_guard  # type: ignore[import-not-found]


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


# --- Module constants -------------------------------------------------------


def test_probe_timeout_seconds_value():
    assert destructive_guard._PROBE_TIMEOUT_SECONDS == 1.0


def test_config_file_names():
    assert destructive_guard._COMMANDS_FILE.name == "destructive-commands.json"
    assert destructive_guard._CAREFUL_FILE.name == "careful-state.json"


def test_load_patterns_uses_inline_defaults_when_config_missing(monkeypatch, tmp_path):
    # Point the config at a nonexistent file so _load_json returns None and
    # the inline fallback lists are returned verbatim — pins every default.
    monkeypatch.setattr(destructive_guard, "_COMMANDS_FILE", tmp_path / "absent.json")
    assert destructive_guard._load_patterns() == (
        ["rm -rf", "rm -r", "rm -fr"],
        ["drop table", "drop database", "truncate"],
        [
            "git push --force",
            "git push -f",
            "git reset --hard",
            "git clean -f",
            "git clean -fd",
            "git checkout -- .",
            "git branch -D",
        ],
        ["kill -9", "killall", "pkill"],
        ["chmod 777"],
        [
            "rm -rf node_modules",
            "rm -rf dist",
            "rm -rf build",
            "rm -rf .cache",
            "rm -rf coverage",
            "rm -rf tmp",
            "rm -rf __pycache__",
        ],
    )


def test_load_patterns_maps_each_config_key(monkeypatch, tmp_path):
    # A distinct marker per key proves each category is read from the right
    # JSON key, in the documented (file, db, git, process, permission, safe)
    # return order.
    config = {
        "file_destruction": ["F1"],
        "database_destruction": ["D1"],
        "git_destruction": ["G1"],
        "process_destruction": ["P1"],
        "permission_escalation": ["E1"],
        "safe_allowlist": ["S1"],
    }
    config_path = tmp_path / "cmds.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(destructive_guard, "_COMMANDS_FILE", config_path)
    assert destructive_guard._load_patterns() == (
        ["F1"],
        ["D1"],
        ["G1"],
        ["P1"],
        ["E1"],
        ["S1"],
    )


# --- Pure helpers -----------------------------------------------------------


def test_read_stdin_returns_empty_on_error(monkeypatch):
    class _Boom:
        def read(self):
            raise OSError("no stdin")

    monkeypatch.setattr("sys.stdin", _Boom())
    assert destructive_guard._read_stdin() == ""


def test_extract_command_variants():
    assert (
        destructive_guard._extract_command({"tool_input": {"command": "rm -rf /"}})
        == "rm -rf /"
    )
    # tool_input not a dict
    assert destructive_guard._extract_command({"tool_input": "notdict"}) == ""
    # command key absent
    assert destructive_guard._extract_command({"tool_input": {}}) == ""
    # command not a string
    assert destructive_guard._extract_command({"tool_input": {"command": 123}}) == ""


def test_careful_active_variants(monkeypatch, tmp_path):
    def _set(content: str) -> None:
        path = tmp_path / "careful.json"
        path.write_text(content, encoding="utf-8")
        monkeypatch.setattr(destructive_guard, "_CAREFUL_FILE", path)

    _set('{"active": true}')
    assert destructive_guard._careful_active() is True
    _set('{"active": false}')
    assert destructive_guard._careful_active() is False
    # A string "true" is treated as active (bash string comparison parity).
    _set('{"active": "true"}')
    assert destructive_guard._careful_active() is True
    _set('{"active": "nope"}')
    assert destructive_guard._careful_active() is False
    _set("{}")
    assert destructive_guard._careful_active() is False
    # Missing config file -> inactive.
    monkeypatch.setattr(destructive_guard, "_CAREFUL_FILE", tmp_path / "absent.json")
    assert destructive_guard._careful_active() is False


def test_run_git_passes_expected_subprocess_args(monkeypatch):
    captured = {}

    def _fake_run(*args, **kwargs):
        captured["cmd"] = args[0]
        captured["kwargs"] = kwargs
        return _FakeCompleted(0, "main\n")

    monkeypatch.setattr(destructive_guard.subprocess, "run", _fake_run)
    assert destructive_guard._run_git(["rev-parse", "--abbrev-ref", "HEAD"]) == "main"
    assert captured["cmd"] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["timeout"] == destructive_guard._PROBE_TIMEOUT_SECONDS
    assert captured["kwargs"]["check"] is False


def test_current_branch_returns_name(monkeypatch):
    captured = {}

    def _fake(args):
        captured["args"] = args
        return "feature/x"

    monkeypatch.setattr(destructive_guard, "_run_git", _fake)
    assert destructive_guard._current_branch() == "feature/x"
    assert captured["args"] == ["rev-parse", "--abbrev-ref", "HEAD"]


def test_current_branch_none_when_no_repo(monkeypatch):
    monkeypatch.setattr(destructive_guard, "_run_git", lambda args: None)
    assert destructive_guard._current_branch() is None


def test_default_branch_symbolic_ref_strips_all_but_last_segment(monkeypatch):
    captured = {}

    def _fake(args):
        captured["args"] = args
        return "origin/release/main" if args[0] == "symbolic-ref" else None

    monkeypatch.setattr(destructive_guard, "_run_git", _fake)
    assert destructive_guard._default_branch() == "main"
    assert captured["args"] == [
        "symbolic-ref",
        "--short",
        "refs/remotes/origin/HEAD",
    ]


def test_default_branch_falls_back_to_master_only(monkeypatch):
    def _fake(args):
        if args[0] == "symbolic-ref":
            return None
        if args == ["rev-parse", "--verify", "--quiet", "refs/heads/master"]:
            return "cafe"
        return None

    monkeypatch.setattr(destructive_guard, "_run_git", _fake)
    assert destructive_guard._default_branch() == "master"


def test_remote_url_passes_expected_args(monkeypatch):
    captured = {}

    def _fake(args):
        captured["args"] = args
        return "git@github.com:org/repo.git"

    monkeypatch.setattr(destructive_guard, "_run_git", _fake)
    assert destructive_guard._remote_url() == "git@github.com:org/repo.git"
    assert captured["args"] == ["remote", "get-url", "origin"]


def test_ci_active_recognizes_truthy_and_falsy_values(monkeypatch):
    for value, expected in [
        ("1", True),
        ("true", True),
        ("  TRUE  ", True),
        ("0", False),
        ("false", False),
        ("FALSE", False),
        ("", False),
    ]:
        monkeypatch.setenv("CI", value)
        assert destructive_guard._ci_active() is expected


def test_matches_any_skips_empty_patterns():
    # The first (empty) pattern is skipped; the real one still matches.
    assert destructive_guard._matches_any("rm -rf x", ["", "rm -rf"]) == "rm -rf"
    assert destructive_guard._matches_any("safe cmd", ["", "nomatch"]) is None


def test_emit_appends_newline(capsys):
    destructive_guard._emit("hello")
    assert capsys.readouterr().out == "hello\n"


def test_load_escalations_filters_invalid_entries(monkeypatch, tmp_path):
    config = {
        "escalations": [
            {"pattern": "git push --force", "when": {}},
            {"no_pattern": "x"},
            "notadict",
            {"pattern": 123},
        ]
    }
    config_path = tmp_path / "cmds.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(destructive_guard, "_COMMANDS_FILE", config_path)
    assert destructive_guard._load_escalations() == [
        {"pattern": "git push --force", "when": {}}
    ]


def test_find_escalation_rule_matches_by_pattern():
    rules = [{"pattern": "a"}, {"pattern": "b", "x": 1}]
    assert destructive_guard._find_escalation_rule(rules, "b") == {"pattern": "b", "x": 1}
    assert destructive_guard._find_escalation_rule(rules, "z") is None


def test_condition_target_branch_default_named_target():
    assert (
        destructive_guard._condition_target_branch_default(
            "git push --force origin main",
            "git push --force origin main",
            "git push --force",
            None,
            "main",
        )
        is True
    )


def test_condition_target_branch_default_bare_on_default_branch():
    assert (
        destructive_guard._condition_target_branch_default(
            "git push --force", "git push --force", "git push --force", "main", "main"
        )
        is True
    )


def test_condition_target_branch_default_bare_off_default_branch():
    assert (
        destructive_guard._condition_target_branch_default(
            "git push --force",
            "git push --force",
            "git push --force",
            "feature",
            "main",
        )
        is False
    )


def test_condition_target_branch_default_unresolved_default_is_false():
    assert (
        destructive_guard._condition_target_branch_default(
            "git push --force", "git push --force", "git push --force", "main", None
        )
        is False
    )


def test_condition_current_branch_default_matrix():
    cond = destructive_guard._condition_current_branch_default
    assert cond("main", "main") is True
    assert cond("feature", "main") is False
    assert cond(None, "main") is False
    assert cond("main", None) is False


def test_rule_escalates_requires_non_empty_when_dict():
    escalates = destructive_guard._rule_escalates
    assert escalates({}, "c", "c", "p", None, None) is False
    assert escalates({"when": {}}, "c", "c", "p", None, None) is False
    assert escalates({"when": "x"}, "c", "c", "p", None, None) is False


def test_rule_escalates_unknown_condition_key_does_not_escalate():
    assert (
        destructive_guard._rule_escalates(
            {"when": {"unknown": "x"}}, "c", "c", "p", "main", "main"
        )
        is False
    )


def test_rule_escalates_target_branch_default_true():
    assert (
        destructive_guard._rule_escalates(
            {"when": {"target_branch": "default"}},
            "git push --force origin main",
            "git push --force origin main",
            "git push --force",
            "main",
            "main",
        )
        is True
    )


def test_override_active_variants(monkeypatch):
    var = destructive_guard._OVERRIDE_ENV_VAR
    monkeypatch.setenv(var, "1")
    assert destructive_guard._override_active() is True
    monkeypatch.setenv(var, " 1 ")
    assert destructive_guard._override_active() is True
    monkeypatch.setenv(var, "0")
    assert destructive_guard._override_active() is False
    monkeypatch.delenv(var, raising=False)
    assert destructive_guard._override_active() is False


# --- main() decision paths --------------------------------------------------


def test_main_empty_command_returns_zero(monkeypatch, capsys):
    _feed(monkeypatch, {"tool_input": {"command": ""}})
    assert destructive_guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_non_matching_command_returns_zero(monkeypatch, capsys):
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    _feed(monkeypatch, {"tool_input": {"command": "ls -la"}})
    assert destructive_guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_warns_on_file_destruction(monkeypatch, capsys):
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_load_escalations", list)
    _feed(monkeypatch, {"tool_input": {"command": "rm -rf /var/data"}})
    assert destructive_guard.main() == 0
    assert (
        "CAUTION: Destructive command detected (File destruction: rm -rf)."
        in capsys.readouterr().out
    )


def test_main_warns_on_database_destruction(monkeypatch, capsys):
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_load_escalations", list)
    _feed(monkeypatch, {"tool_input": {"command": "drop table users"}})
    assert destructive_guard.main() == 0
    assert (
        "CAUTION: Destructive command detected (Database destruction: drop table)."
        in capsys.readouterr().out
    )


def test_main_warn_full_output_and_boundary_event(monkeypatch, capsys):
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_load_escalations", list)
    events = []
    monkeypatch.setattr(
        destructive_guard, "emit_boundary_event", lambda *a, **k: events.append(a)
    )
    _feed(
        monkeypatch,
        {"tool_input": {"command": "kill -9 1234"}, "cwd": "/wd", "session_id": "s1"},
    )
    assert destructive_guard.main() == 0
    assert capsys.readouterr().out == (
        "CAUTION: Destructive command detected (Process destruction: kill -9).\n"
        "Command: kill -9 1234\n"
        "This action is hard to reverse. Confirm with the user before proceeding.\n"
    )
    assert events == [
        ("/wd", "destructive_guard", "Bash", "warn", "Process destruction: kill -9", "s1")
    ]


def test_main_warn_defaults_cwd_to_dot_and_session_to_none(monkeypatch, capsys):
    # No cwd / session_id in the payload — cwd falls back to ".", session
    # to None, both observable only through the boundary event.
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_load_escalations", list)
    events = []
    monkeypatch.setattr(
        destructive_guard, "emit_boundary_event", lambda *a, **k: events.append(a)
    )
    _feed(monkeypatch, {"tool_input": {"command": "kill -9 1"}})
    assert destructive_guard.main() == 0
    assert events[0][0] == "."
    assert events[0][5] is None


def test_main_careful_full_output_and_boundary_event(monkeypatch, capsys):
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: True)
    events = []
    monkeypatch.setattr(
        destructive_guard, "emit_boundary_event", lambda *a, **k: events.append(a)
    )
    _feed(
        monkeypatch,
        {"tool_input": {"command": "kill -9 1234"}, "cwd": "/wd", "session_id": "s1"},
    )
    assert destructive_guard.main() == 2
    assert capsys.readouterr().out == (
        "BLOCKED: Destructive command detected (Process destruction: kill -9).\n"
        "Command: kill -9 1234\n"
        "Careful mode is active. This command has been blocked.\n"
        "Use /careful off to disable careful mode, or confirm with the user.\n"
    )
    assert events == [
        ("/wd", "destructive_guard", "Bash", "block", "Process destruction: kill -9", "s1")
    ]


def test_main_escalation_block_emits_full_output(monkeypatch, capsys):
    monkeypatch.setattr(destructive_guard, "_careful_active", lambda: False)
    monkeypatch.setattr(destructive_guard, "_current_branch", lambda: "main")
    monkeypatch.setattr(destructive_guard, "_default_branch", lambda: "main")
    monkeypatch.delenv(destructive_guard._OVERRIDE_ENV_VAR, raising=False)
    _feed(monkeypatch, {"tool_input": {"command": "git push --force origin main"}})
    assert destructive_guard.main() == 2
    assert capsys.readouterr().out == (
        "BLOCKED: Destructive command detected (Git destruction: git push --force).\n"
        "Command: git push --force origin main\n"
        "This command targets the default branch (main); force-push, reset, and "
        "branch-delete are hard-blocked on the default branch regardless of "
        "careful mode.\n"
        "Set DEV_TEAM_GUARD_OVERRIDE=1 for this single command to override, or "
        "confirm with the user.\n"
    )
