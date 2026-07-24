"""Tests for the opt-in telemetry beacon (issues #106, #135): default-off
consent, command capture, distinct skill capture (incl. agent-/auto-invoked),
gate fired/bypassed capture (incl. trailing -n), privacy (no payloads), and
the report aggregation.

Ported from tests/repo/telemetry_tests.bats (issue #672).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "telemetry.py"
REPORT = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "telemetry_report.py"


def _enable(d: Path) -> None:
    (d / ".claude").mkdir(parents=True, exist_ok=True)
    (d / ".claude" / "telemetry.json").write_text('{"enabled":true}')


def _send(payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env if env is not None else os.environ.copy(),
    )


def _log_lines(d: Path) -> list[str]:
    return (d / "metrics" / "telemetry.jsonl").read_text().splitlines()


def test_telemetry_off_by_default_nothing_is_recorded(tmp_path: Path) -> None:
    _send(
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/specs",
            "cwd": str(tmp_path),
        }
    )
    assert not (tmp_path / "metrics" / "telemetry.jsonl").exists()


def test_telemetry_enabling_via_claude_telemetry_json_records_a_command_event(
    tmp_path: Path,
) -> None:
    _enable(tmp_path)
    _send(
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/code-review --scope x",
            "cwd": str(tmp_path),
        }
    )
    assert (tmp_path / "metrics" / "telemetry.jsonl").is_file()
    entry = json.loads(_log_lines(tmp_path)[0])
    assert f"{entry['event']} {entry['name']}" == "command code-review"


def test_telemetry_env_dev_team_telemetry_on_also_enables(tmp_path: Path) -> None:
    env = {**os.environ, "DEV_TEAM_TELEMETRY": "on"}
    res = _send(
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/build",
            "cwd": str(tmp_path),
        },
        env=env,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    entry = json.loads(_log_lines(tmp_path)[0])
    assert entry["name"] == "build"


def test_telemetry_records_gate_fired_vs_bypassed_for_git_commit(
    tmp_path: Path,
) -> None:
    _enable(tmp_path)
    _send(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m hello"},
            "cwd": str(tmp_path),
        }
    )
    _send(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit --no-verify -m skip"},
            "cwd": str(tmp_path),
        }
    )
    outcomes = [json.loads(line)["outcome"] for line in _log_lines(tmp_path)]
    assert outcomes == ["fired", "bypassed"]


def test_telemetry_privacy_no_prompt_text_command_string_or_paths_in_the_log(
    tmp_path: Path,
) -> None:
    _enable(tmp_path)
    _send(
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "/specs SECRET_PROMPT_TEXT /home/u/secret",
            "cwd": str(tmp_path),
        }
    )
    _send(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m SECRET_MESSAGE"},
            "cwd": str(tmp_path),
        }
    )
    log_text = (tmp_path / "metrics" / "telemetry.jsonl").read_text()
    assert "SECRET_PROMPT_TEXT" not in log_text
    assert "SECRET_MESSAGE" not in log_text
    assert "/home/u/secret" not in log_text
    # Only the documented keys are present.
    entries = [json.loads(line) for line in log_text.splitlines()]
    expected_keys = {"event", "name", "outcome", "plugin_version", "ts"}
    assert all(set(entry.keys()) == expected_keys for entry in entries)


def test_telemetry_non_bash_pretooluse_and_non_slash_prompts_record_nothing(
    tmp_path: Path,
) -> None:
    _enable(tmp_path)
    _send(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "x"},
            "cwd": str(tmp_path),
        }
    )
    _send(
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "just a normal question",
            "cwd": str(tmp_path),
        }
    )
    assert not (tmp_path / "metrics" / "telemetry.jsonl").exists()


def test_telemetry_pretooluse_skill_records_a_distinct_skill_event(
    tmp_path: Path,
) -> None:
    _enable(tmp_path)
    _send(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Skill",
            "tool_input": {"skill": "code-review"},
            "cwd": str(tmp_path),
        }
    )
    entry = json.loads(_log_lines(tmp_path)[0])
    assert f"{entry['event']} {entry['name']}" == "skill code-review"


def test_telemetry_bypass_detection_catches_a_trailing_n_flag_135(
    tmp_path: Path,
) -> None:
    _enable(tmp_path)
    _send(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m msg -n"},
            "cwd": str(tmp_path),
        }
    )
    entry = json.loads(_log_lines(tmp_path)[0])
    assert entry["outcome"] == "bypassed"


def test_telemetry_a_real_filename_containing_n_does_not_false_bypass(
    tmp_path: Path,
) -> None:
    _enable(tmp_path)
    _send(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'add foo-name.js'"},
            "cwd": str(tmp_path),
        }
    )
    entry = json.loads(_log_lines(tmp_path)[0])
    assert entry["outcome"] == "fired"


def test_report_aggregates_usage_and_bypass_rate_with_skills_distinct_from_commands(
    tmp_path: Path,
) -> None:
    log = tmp_path / "t.jsonl"
    log.write_text(
        '{"event":"command","name":"specs","outcome":"invoked","plugin_version":"1"}\n'
        '{"event":"command","name":"specs","outcome":"invoked","plugin_version":"1"}\n'
        '{"event":"command","name":"build","outcome":"invoked","plugin_version":"1"}\n'
        '{"event":"skill","name":"token-efficiency-review","outcome":"invoked","plugin_version":"1"}\n'
        '{"event":"skill","name":"token-efficiency-review","outcome":"invoked","plugin_version":"1"}\n'
        '{"event":"gate","name":"pre-commit-review","outcome":"fired","plugin_version":"1"}\n'
        '{"event":"gate","name":"pre-commit-review","outcome":"bypassed","plugin_version":"1"}\n'
        '{"event":"gate","name":"pre-commit-review","outcome":"bypassed","plugin_version":"1"}\n'
    )
    res = subprocess.run(
        [sys.executable, str(REPORT), "--log", str(log), "--json"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(res.stdout)
    assert data["command_usage"]["specs"] == 2
    assert data["skill_usage"]["token-efficiency-review"] == 2
    # skills are NOT conflated into command_usage
    assert "token-efficiency-review" not in data["command_usage"]
    assert data["gates"]["pre-commit-review"]["bypass_rate"] == 0.6667


def test_report_disabled_no_log_says_nothing_left_the_machine(tmp_path: Path) -> None:
    res = subprocess.run(
        [sys.executable, str(REPORT), "--log", str(tmp_path / "none.jsonl")],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Nothing has left the machine" in res.stdout


def test_settings_json_registers_telemetry_py_on_userpromptsubmit_and_pretooluse_bash() -> (
    None
):
    settings = json.loads(
        (REPO_ROOT / "plugins" / "dev-team" / "settings.json").read_text()
    )
    upsubmit_hooks = [
        h["command"]
        for entry in settings["hooks"]["UserPromptSubmit"]
        for h in entry["hooks"]
    ]
    assert any("telemetry.py" in c for c in upsubmit_hooks)
    pretooluse_bash_hooks = [
        h["command"]
        for entry in settings["hooks"]["PreToolUse"]
        if entry.get("matcher") == "Bash"
        for h in entry["hooks"]
    ]
    assert any("telemetry.py" in c for c in pretooluse_bash_hooks)


def test_settings_json_registers_telemetry_py_on_pretooluse_skill_135() -> None:
    settings = json.loads(
        (REPO_ROOT / "plugins" / "dev-team" / "settings.json").read_text()
    )
    pretooluse_skill_hooks = [
        h["command"]
        for entry in settings["hooks"]["PreToolUse"]
        if entry.get("matcher") == "Skill"
        for h in entry["hooks"]
    ]
    assert any("telemetry.py" in c for c in pretooluse_skill_hooks)
