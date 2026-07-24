"""Guard the shipped hook config against the Claude Code hook-config schema.

Regression test for #1227: v10.14.x shipped `settings.json`/`hooks.json` with
an invalid hook event (`SessionStop`) and `"matcher": null` on the `Stop` and
`SubagentStop` groups. The CLI's schema rejected both, so the whole plugin
`failed to load` — no hooks, agents, or skills available.

These two checks reproduce the CLI's two rejection classes without needing the
CLI itself:

1. every top-level key under `hooks` must be a known Claude Code hook event;
2. no hook group may carry `matcher: null` — the schema wants a string or the
   key omitted entirely.

Both the plugin-local `settings.json` and the marketplace `hooks/hooks.json`
are validated, since they are hand-maintained mirrors and drift silently.

If Claude Code adds a new hook event, extend VALID_HOOK_EVENTS below — this is
a deliberate known-good allowlist, not an auto-derived one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
HOOK_FILES = [PLUGIN / "settings.json", PLUGIN / "hooks" / "hooks.json"]

# The hook events Claude Code's hook-config schema accepts. Sourced from the
# CLI's own error enum (#1227). Add new events here when the CLI adds them.
VALID_HOOK_EVENTS = frozenset(
    {
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "PostToolBatch",
        "Notification",
        "UserPromptSubmit",
        "UserPromptExpansion",
        "SessionStart",
        "SessionEnd",
        "Stop",
        "StopFailure",
        "SubagentStart",
        "SubagentStop",
        "PreCompact",
        "PostCompact",
        "PermissionRequest",
        "PermissionDenied",
        "Setup",
        "TeammateIdle",
        "TaskCreated",
        "TaskCompleted",
        "Elicitation",
        "ElicitationResult",
        "ConfigChange",
        "WorktreeCreate",
        "WorktreeRemove",
        "InstructionsLoaded",
        "CwdChanged",
        "FileChanged",
        "MessageDisplay",
    }
)


def _hooks(path: Path) -> dict:
    return json.loads(path.read_text()).get("hooks", {})


@pytest.mark.parametrize("path", HOOK_FILES, ids=lambda p: p.name)
def test_every_hook_event_key_is_valid(path: Path) -> None:
    invalid = sorted(set(_hooks(path)) - VALID_HOOK_EVENTS)
    assert not invalid, (
        f"{path.relative_to(REPO_ROOT)} registers unknown hook event(s) "
        f"{invalid}; the CLI schema will reject the plugin. Valid events: "
        f"{sorted(VALID_HOOK_EVENTS)}"
    )


@pytest.mark.parametrize("path", HOOK_FILES, ids=lambda p: p.name)
def test_no_hook_group_has_null_matcher(path: Path) -> None:
    offenders = [
        event
        for event, groups in _hooks(path).items()
        for group in groups
        if "matcher" in group and group["matcher"] is None
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} has `\"matcher\": null` under "
        f"{sorted(set(offenders))}; the schema requires a string or an omitted "
        f"key. Remove the matcher key for non-tool events."
    )
