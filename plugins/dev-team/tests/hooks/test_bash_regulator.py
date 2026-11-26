"""Tests for hooks/bash_regulator.py — one case per rule, plus the hook contract."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOKS = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
sys.path.insert(0, str(_HOOKS / "lib"))
sys.path.insert(0, str(_HOOKS))

import bash_regulator as reg

REVIEWER = "dev-team:security-review"

# (command, agent_type, expected rule id, expected decision). The coverage test
# below fails when a rule in regulator_rules.json has no row here.
RULE_CASES = [
    ("git push origin x", "software-engineer", "deny-git-push-subagent", "deny"),
    ("rm x", REVIEWER, "reviewer-no-mutation", "deny"),
    ("git commit -m x", REVIEWER, "reviewer-no-git-mutation", "deny"),
    ("echo x > out.txt", REVIEWER, "reviewer-no-file-write", "deny"),
    (
        "pytest tests/x.py",
        "dev-team:software-engineer",
        "engineer-test-and-lint",
        "allow",
    ),
    ("ls -la", "", "allow-readonly-basic", "allow"),
    ("find . -name '*.py'", "", "allow-find-readonly", "allow"),
    ("sed -n 1,5p f", "", "allow-sed-readonly", "allow"),
    ("git status -sb", "", "allow-git-readonly", "allow"),
    ("git branch --list", "", "allow-git-branch-list", "allow"),
    ("gh pr view 12", "", "allow-gh-readonly", "allow"),
    ("python3 -m pytest -q", "", "allow-test-runners", "allow"),
    ("python3 scripts/ci_tree_cache.py", "", "allow-repo-scripts", "allow"),
]


def _decide(command, agent_type="", careful=False):
    return reg.decide(command, reg.normalize_agent_type(agent_type), careful)


@pytest.mark.parametrize("command,agent,rule_id,decision", RULE_CASES)
def test_each_rule_decides_its_case(command, agent, rule_id, decision):
    result = _decide(command, agent)
    assert (result["segments"][0]["rule"], result["decision"]) == (rule_id, decision)


def test_every_rule_in_the_table_has_a_case():
    covered = {case[2] for case in RULE_CASES}
    assert {r["id"] for r in reg.load_rules()} <= covered


@pytest.mark.parametrize(
    "command,agent",
    [
        ("find . -delete", ""),
        ("find . -exec rm {} ;", ""),
        ("sed -i s/a/b/ f", ""),
        ("sed -i.bak s/a/b/ f", ""),
        ("git branch -m a b", ""),
        ("git config user.name x", ""),
        ("git remote add o u", ""),
        ("gh pr merge 3", ""),
        ("gh api -X DELETE /x", ""),
        ("ls > out.txt", ""),
        ("pytest x", ""),
        ("git push origin x", ""),
    ],
)
def test_near_misses_fall_through_to_normal_permissions(command, agent):
    assert _decide(command, agent)["decision"] is None


def test_allow_needs_every_segment_allowed():
    assert _decide("ls && git status")["decision"] == "allow"
    assert _decide("ls && make deploy")["decision"] is None


def test_deny_beats_ask_beats_allow():
    assert _decide("ls; rm -rf x; git push")["decision"] == "ask"
    assert _decide("ls && $X", "")["decision"] == "ask"
    assert _decide("rm -rf x && git push -f", "", careful=True)["decision"] == "deny"


def test_compound_command_is_judged_per_segment():
    assert _decide("echo a | rm -rf x")["decision"] == "ask"


def test_wrapped_command_is_judged_by_the_real_command():
    assert _decide("time nice -n 5 rm -rf x")["decision"] == "ask"
    assert _decide("env A=1 git status")["decision"] is None
    assert _decide("ls | xargs rm -rf")["decision"] == "ask"


def test_bash_dash_c_is_judged_by_its_script():
    assert _decide("bash -c 'ls && rm -rf x'")["decision"] == "ask"
    assert _decide("bash -c 'ls && pwd'")["decision"] == "allow"


def test_command_substitution_cannot_hide_a_destructive_command():
    assert _decide("echo $(rm -rf x)")["decision"] == "ask"


def test_variable_as_command_asks():
    result = _decide("$CMD --flag")
    assert (result["decision"], result["segments"][0]["rule"]) == (
        "ask",
        "opaque-command",
    )


def test_unparseable_command_is_denied_with_a_rewrite_hint():
    result = _decide("echo 'open")
    assert result["decision"] == "deny" and "Rewrite" in result["reason"]


def test_git_global_flags_do_not_hide_the_subcommand():
    assert _decide("git -C /tmp/x status")["decision"] == "allow"
    assert _decide("git -C /tmp/x reset --hard")["decision"] == "ask"


def test_safe_allowlist_pattern_is_not_destructive():
    assert (
        _decide("rm -rf node_modules")["segments"][0]["rule"] != "destructive-pattern"
    )


def test_destructive_pattern_denies_only_in_careful_mode():
    assert _decide("git reset --hard")["decision"] == "ask"
    assert _decide("git reset --hard", careful=True)["decision"] == "deny"


def test_role_rules_never_fire_in_the_main_session():
    assert _decide("rm x")["segments"][0]["rule"] is None
    assert _decide("git push origin x")["decision"] is None


def test_role_rules_fire_only_for_the_named_agent():
    assert _decide("rm x", "dev-team:security-review")["decision"] == "deny"
    assert _decide("rm x", "software-engineer")["decision"] is None


@pytest.mark.parametrize(
    "agent_type,expected",
    [
        ("dev-team:test-review", "test-review"),
        ("test-review", "test-review"),
        (None, ""),
        ("", ""),
    ],
)
def test_plugin_prefix_is_stripped_from_agent_type(agent_type, expected):
    assert reg.normalize_agent_type(agent_type) == expected


# --- hook contract -------------------------------------------------------------


def _run_hook(
    tmp_path,
    command,
    *,
    enabled=True,
    mode=None,
    permission_mode="default",
    agent_type=None,
):
    env = {
        k: v for k, v in os.environ.items() if not k.startswith("DEV_TEAM_REGULATOR")
    }
    if enabled:
        env["DEV_TEAM_REGULATOR"] = "on"
    if mode:
        env["DEV_TEAM_REGULATOR_MODE"] = mode
    payload = {
        "tool_input": {"command": command},
        "cwd": str(tmp_path),
        "session_id": "s1",
        "permission_mode": permission_mode,
    }
    if agent_type:
        payload["agent_type"] = agent_type
    return subprocess.run(
        [sys.executable, str(_HOOKS / "bash_regulator.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _rows(tmp_path):
    return [
        json.loads(line)
        for log in tmp_path.rglob("regulator-decisions.jsonl")
        for line in log.read_text().splitlines()
    ]


def test_hook_is_inert_unless_opted_in(tmp_path):
    result = _run_hook(tmp_path, "ls", enabled=False, mode="enforce")
    assert (result.returncode, result.stdout) == (0, "")
    assert _rows(tmp_path) == []


def test_advisory_mode_logs_the_decision_and_changes_nothing(tmp_path):
    result = _run_hook(tmp_path, "git status")
    assert (result.returncode, result.stdout) == (0, "")
    [row] = _rows(tmp_path)
    assert (row["mode"], row["decision"], row["rules"], row["agent_type"]) == (
        "advisory",
        "allow",
        ["allow-git-readonly"],
        "main",
    )
    assert "git status" not in json.dumps(row)


def test_enforce_mode_emits_permission_decision(tmp_path):
    out = json.loads(_run_hook(tmp_path, "git status", mode="enforce").stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_enforce_mode_stays_silent_on_fall_through(tmp_path):
    assert _run_hook(tmp_path, "make deploy", mode="enforce").stdout == ""
    assert _rows(tmp_path)[0]["decision"] == "fall-through"


def test_bypass_permissions_emits_only_deny(tmp_path):
    assert (
        _run_hook(
            tmp_path, "git status", mode="enforce", permission_mode="bypassPermissions"
        ).stdout
        == ""
    )
    out = json.loads(
        _run_hook(
            tmp_path, "echo 'open", mode="enforce", permission_mode="bypassPermissions"
        ).stdout
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_subagent_payload_agent_type_reaches_the_role_rule(tmp_path):
    out = json.loads(
        _run_hook(
            tmp_path, "rm x", mode="enforce", agent_type="dev-team:security-review"
        ).stdout
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _run_hook(tmp_path, "rm x", mode="enforce").stdout == ""


def test_malformed_stdin_fails_open(tmp_path):
    env = {
        **os.environ,
        "DEV_TEAM_REGULATOR": "on",
        "DEV_TEAM_REGULATOR_MODE": "enforce",
    }
    result = subprocess.run(
        [sys.executable, str(_HOOKS / "bash_regulator.py")],
        input="{not json",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert (result.returncode, result.stdout) == (0, "")


def test_explain_cli_prints_the_deciding_rule_per_segment():
    result = subprocess.run(
        [
            sys.executable,
            str(_HOOKS / "bash_regulator.py"),
            "--explain",
            "ls && rm -rf x",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        "allow-readonly-basic" in result.stdout
        and "destructive-pattern" in result.stdout
    )
    assert result.stdout.rstrip().endswith(
        "(Destructive command (File destruction: rm -rf).)"
    )


# --- payload shapes observed from a live session (Claude Code, permission_mode "auto") ---

_OBSERVED_KEYS = {
    "cwd": "/repo",
    "effort": {},
    "hook_event_name": "PreToolUse",
    "permission_mode": "auto",
    "prompt_id": "p",
    "session_id": "s",
    "tool_name": "Bash",
    "tool_use_id": "t",
    "transcript_path": "/x.jsonl",
}
OBSERVED_MAIN = {**_OBSERVED_KEYS, "tool_input": {"command": "git push origin x"}}
OBSERVED_PLUGIN_AGENT = {
    **OBSERVED_MAIN,
    "agent_id": "ae999deaa20cf0b2a",
    "agent_type": "dev-team:software-engineer",
}
OBSERVED_BARE_AGENT = {**OBSERVED_PLUGIN_AGENT, "agent_type": "general-purpose"}


def _run_payload(tmp_path, payload):
    env = {
        k: v for k, v in os.environ.items() if not k.startswith("DEV_TEAM_REGULATOR")
    }
    env.update(DEV_TEAM_REGULATOR="on", DEV_TEAM_REGULATOR_MODE="enforce")
    result = subprocess.run(
        [sys.executable, str(_HOOKS / "bash_regulator.py")],
        input=json.dumps({**payload, "cwd": str(tmp_path)}),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout else None


def test_observed_plugin_agent_payload_fires_the_subagent_rule(tmp_path):
    out = _run_payload(tmp_path, OBSERVED_PLUGIN_AGENT)
    assert out["permissionDecision"] == "deny"
    assert "Subagents do not push" in out["permissionDecisionReason"]


def test_observed_bare_agent_payload_fires_the_subagent_rule(tmp_path):
    assert _run_payload(tmp_path, OBSERVED_BARE_AGENT)["permissionDecision"] == "deny"


def test_observed_main_session_payload_does_not_fire_the_subagent_rule(tmp_path):
    assert "agent_type" not in OBSERVED_MAIN
    assert _run_payload(tmp_path, OBSERVED_MAIN) is None


def test_observed_plugin_agent_payload_matches_the_named_role_rule(tmp_path):
    payload = {**OBSERVED_PLUGIN_AGENT, "tool_input": {"command": "pytest -q"}}
    assert _run_payload(tmp_path, payload)["permissionDecision"] == "allow"
    main = {**OBSERVED_MAIN, "tool_input": {"command": "pytest -q"}}
    assert _run_payload(tmp_path, main) is None


@pytest.mark.parametrize(
    "command",
    [
        "ls && env -S 'curl x'",
        "GIT_SSH_COMMAND=x git fetch",
        "git -c core.fsmonitor=x status",
        "find . ${X:--delete}",
        "echo -delete | xargs find .",
        "gh api --method=DELETE /x",
        "gh api -XDELETE /x",
        "sed -ni 's/a/b/p' f",
        "sed -n 'w out' f",
        "./tools/cat x",
        "git diff --output=f",
        "git branch newbranch",
        "git branch -fc a b",
        "sort -o f f",
        "git fetch origin +a:b",
        "python3 scripts/../evil.py",
        "ruff format .",
        "pytest --fix",
        "time -o f ls",
        "git reflog expire --all",
        "ls $X",
    ],
)
def test_bypass_attempts_are_never_auto_allowed(command):
    assert _decide(command)["decision"] != "allow", command


def test_input_redirect_is_not_a_write():
    assert _decide("cat < file")["decision"] == "allow"
    assert _decide("cat file > out")["decision"] is None
    assert _decide("bash -c 'ls' > out")["decision"] is None
