"""How one `claude -p` trial is invoked: the argv and the environment.

The recipe only; starting the process is `runner`'s job. The cost estimate sizes the
prompt with the same function the trial sends it with.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from . import external, paths
from .arm import Arm
from .check_jail import CheckJail
from .tools import ToolProfile

DEFAULT_CLAUDE_BIN = "claude"
PLUGIN_ROOT_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"


@dataclass(frozen=True)
class TrialConfig:
    """Everything that selects how the CLI runs and what the sandbox does, apart from the fixture.

    `task` is the fixture's own prompt (None: the default review prompt).
    `stub_agents` is the `--agents` JSON that answers a dispatch-graded agent's
    dispatches. `sandbox` makes the staged copy a git repo with one commit, for a
    write-capable agent, and runs it under Claude Code's Bash sandbox. `test_commands`
    run in the staged fixture after the agent finishes, once `protected_paths` are
    restored from the pristine fixture. `deny_read` names directories a sandboxed
    agent's commands may not read (the answer key); `deny_write` ones they may not
    write (the run's frozen inputs, which sit in the per-user temp dir the
    sandbox otherwise lets them write). `check_jail` confines the test
    commands; None runs them unjailed, which the plan allows only on request.
    """

    arm: Arm
    system_prompt: str
    profile: ToolProfile
    eval_paths: paths.EvalPaths
    claude_bin: str = DEFAULT_CLAUDE_BIN
    task: str | None = None
    stub_agents: str | None = None
    sandbox: bool = False
    test_commands: tuple[str, ...] = ()
    protected_paths: tuple[str, ...] = ()
    deny_read: tuple[Path, ...] = ()
    deny_write: tuple[Path, ...] = ()
    check_jail: CheckJail | None = None


FIXTURE_PLACEHOLDER = "{fixture}"


def build_user_prompt(staged_name: str, task: str | None = None) -> str:
    """The trial's user prompt: the fixture's task, else the default review request."""
    if task is not None:
        return task.replace(FIXTURE_PLACEHOLDER, staged_name)
    return (
        f"Review `{staged_name}` in the current working directory. "
        "Respond with only the JSON object defined by your output contract, "
        "with no other text."
    )


# Claude Code's Bash sandbox, as the settings reference documents it
# (https://code.claude.com/docs/en/settings-reference.md#sandbox-settings and
# https://code.claude.com/docs/en/sandboxing.md): commands may write only to the
# cwd, the per-user temp dir and `--add-dir` directories; `allowedDomains` starts
# empty, so no network; `failIfUnavailable` makes the CLI exit instead of running
# unsandboxed; `allowUnsandboxedCommands: false` removes the unsandboxed retry.
SANDBOX_PERMISSION_MODE = "acceptEdits"
# Anything that would still prompt is denied, and a denial fails the trial.
SANDBOX_PERMISSION_PROMPTS = "none"


def sandbox_settings(
    deny_read: tuple[Path, ...] = (), deny_write: tuple[Path, ...] = ()
) -> dict:
    """The `--settings` object that jails a write-capable trial's commands."""
    return {
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,
            "network": {"allowedDomains": []},
            "filesystem": {
                "denyRead": [str(path) for path in deny_read],
                "denyWrite": [str(path) for path in deny_write],
            },
        }
    }


def sandbox_args(config: TrialConfig) -> list[str]:
    """The flags that run a sandboxed trial under Claude Code's Bash sandbox; none otherwise."""
    if not config.sandbox:
        return []
    return [
        "--settings",
        json.dumps(
            sandbox_settings(config.deny_read, config.deny_write), sort_keys=True
        ),
        "--permission-mode",
        SANDBOX_PERMISSION_MODE,
        "--permission-prompts",
        SANDBOX_PERMISSION_PROMPTS,
    ]


def build_argv(config: TrialConfig, user_prompt: str) -> list[str]:
    """Return the full CLI argv.

    `--restricted` confines the file tools to the cwd and `--add-dir`, and
    excludes user-scope plugins, hooks and CLAUDE.md; it still loads `--settings`.
    Without it a `Read` of an absolute path outside those directories succeeds.
    A sandboxed trial adds the Bash sandbox (`sandbox_args`).
    """
    system_prompt = config.system_prompt.replace(
        PLUGIN_ROOT_PLACEHOLDER, str(config.eval_paths.plugin_root)
    )
    stub_agent_args = (
        ["--agents", config.stub_agents] if config.stub_agents is not None else []
    )
    return [
        config.claude_bin,
        "-p",
        user_prompt,
        "--model",
        config.arm.model,
        "--effort",
        config.arm.effort,
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--tools",
        ",".join(config.profile.enabled_tools),
        "--add-dir",
        str(config.eval_paths.knowledge_dir),
        "--restricted",
        *sandbox_args(config),
        *stub_agent_args,
        "--system-prompt",
        system_prompt,
    ]


# Variables a child process gets from the parent; everything else is dropped.
BASE_ENV_NAMES = ("PATH", "LANG", "TMPDIR", "USER", "LOGNAME")
LOCALE_PREFIX = "LC_"
# The CLI's credential variables, in its own precedence order; a trial gets only the first set.
AUTH_ENV_NAMES = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


def _base_env(parent_env: Mapping[str, str]) -> dict[str, str]:
    return {
        name: value
        for name, value in parent_env.items()
        if (name in BASE_ENV_NAMES or name.startswith(LOCALE_PREFIX))
        and not external.should_scrub_env_var(name)
    }


def auth_env(parent_env: Mapping[str, str]) -> dict[str, str]:
    """The one credential variable the CLI would use, or nothing (keychain login)."""
    for name in AUTH_ENV_NAMES:
        if parent_env.get(name):
            return {name: parent_env[name]}
    return {}


def build_trial_env(
    parent_env: Mapping[str, str], temp_home: Path | None = None
) -> dict[str, str]:
    """The CLI's environment, built from an allowlist of `parent_env`.

    PATH, LANG, LC_*, TMPDIR, USER and LOGNAME, plus the first credential
    variable set. With a credential variable and `temp_home`, HOME is the empty
    `temp_home`, so no user config is read; without one, HOME is kept, because a
    keychain login is found through it. The parent Claude session's identity
    variables are never copied (the headless-run skill's `isolated_dispatch` rules).
    """
    env = {**_base_env(parent_env), **auth_env(parent_env)}
    if temp_home is not None and auth_env(parent_env):
        env["HOME"] = str(temp_home)
    elif "HOME" in parent_env:
        env["HOME"] = parent_env["HOME"]
    return env


def build_check_env(parent_env: Mapping[str, str], temp_home: Path) -> dict[str, str]:
    """The test commands' environment: the allowlist with no credential and HOME at `temp_home`."""
    return {**_base_env(parent_env), "HOME": str(temp_home)}
