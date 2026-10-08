"""How one `claude -p` trial is invoked: the argv and the environment.

The recipe only; starting the process is `runner`'s job. The cost estimate sizes the
prompt with the same function the trial sends it with.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from . import external, paths
from .arm import Arm
from .tools import ToolProfile

DEFAULT_CLAUDE_BIN = "claude"
PLUGIN_ROOT_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"


@dataclass(frozen=True)
class TrialConfig:
    """Everything that selects how the CLI runs, apart from the fixture."""

    arm: Arm
    system_prompt: str
    profile: ToolProfile
    eval_paths: paths.EvalPaths
    claude_bin: str = DEFAULT_CLAUDE_BIN


def build_user_prompt(staged_name: str) -> str:
    return (
        f"Review `{staged_name}` in the current working directory. "
        "Respond with only the JSON object defined by your output contract, "
        "with no other text."
    )


def build_argv(config: TrialConfig, user_prompt: str) -> list[str]:
    """Return the full CLI argv.

    `--restricted` confines the file tools to the cwd and `--add-dir`, and
    excludes user-scope plugins, hooks and CLAUDE.md. Without it a `Read` of an
    absolute path outside those directories succeeds.
    """
    system_prompt = config.system_prompt.replace(
        PLUGIN_ROOT_PLACEHOLDER, str(config.eval_paths.plugin_root)
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
        "--system-prompt",
        system_prompt,
    ]


def build_trial_env(parent_env: Mapping[str, str]) -> dict[str, str]:
    """Return `parent_env` without the parent Claude session's identity variables.

    The scrub rules come from the headless-run skill's `isolated_dispatch`. HOME
    is kept so authentication works; `--restricted` already excludes user-scope
    config, hooks and CLAUDE.md.
    """
    return {
        name: value
        for name, value in parent_env.items()
        if not external.should_scrub_env_var(name)
    }
