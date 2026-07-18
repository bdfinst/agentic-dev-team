"""Structural guards for plugins/dev-team/hooks/hooks.json (#1178).

Current Claude Code loads plugin hooks from `hooks/hooks.json` (the
documented plugin-hooks mechanism), NOT from a plugin-root `settings.json`
— so a registration that exists only in settings.json is silently dead.
These tests pin three things:

  1. hooks.json exists, is valid, and every command routes through
     ${CLAUDE_PLUGIN_ROOT} (plugin hooks run with the project dir as CWD,
     so CWD-relative script paths would break).
  2. hooks.json and settings.json register the same scripts at the same
     lifecycle points (settings.json is kept as an older-CLI mirror; the
     two must never drift).
  3. The subagent-dispatch matcher covers BOTH dispatch tool names —
     "Task" (pre-2.1.63) and "Agent" (post-rename) — so a harness rename
     can't silently kill model routing again.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "plugins" / "dev-team"
HOOKS_JSON = PLUGIN / "hooks" / "hooks.json"
SETTINGS_JSON = PLUGIN / "settings.json"

DISPATCH_TOOL_NAMES = ("Agent", "Task")
DISPATCH_HOOK_SCRIPTS = ("agent_model_resolve.py", "context_ceiling_guard.py")


def _load_hooks(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["hooks"]


def _script_names(entry: dict) -> list[str]:
    """Basenames of the .py scripts an entry's commands invoke."""
    names = []
    for hook in entry.get("hooks", []):
        found = re.findall(r"([A-Za-z0-9_]+\.py)", hook.get("command", ""))
        assert found, f"no .py script in command: {hook.get('command')!r}"
        names.append(found[-1])
    return names


def _shape(hooks: dict) -> dict:
    """Comparable shape: event -> [(matcher, [script, ...]), ...]."""
    return {
        event: [(entry.get("matcher"), _script_names(entry)) for entry in entries]
        for event, entries in hooks.items()
    }


def test_hooks_json_exists_and_has_hooks_key() -> None:
    assert HOOKS_JSON.is_file(), (
        "plugins/dev-team/hooks/hooks.json is missing — plugin hooks are "
        "only loaded from this file on current Claude Code (#1178); a "
        "settings.json-only registration ships a dead hook layer."
    )
    assert isinstance(_load_hooks(HOOKS_JSON), dict)


def test_every_hooks_json_command_routes_through_plugin_root() -> None:
    for event, entries in _load_hooks(HOOKS_JSON).items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                cmd = hook["command"]
                assert "${CLAUDE_PLUGIN_ROOT}" in cmd, (
                    f"{event}: command must be anchored to "
                    f"${{CLAUDE_PLUGIN_ROOT}} (plugin hooks run from the "
                    f"project dir, not the plugin root): {cmd!r}"
                )
                assert "py.sh" in cmd, (
                    f"{event}: command must route through the py.sh "
                    f"interpreter shim (#1078): {cmd!r}"
                )


def test_hooks_json_mirrors_settings_json_registrations() -> None:
    """settings.json stays as the older-CLI mirror — same events, same
    matchers, same scripts in the same order. Only the path anchoring
    differs."""
    assert _shape(_load_hooks(HOOKS_JSON)) == _shape(_load_hooks(SETTINGS_JSON))


def _dispatch_entries(hooks: dict) -> list[dict]:
    """PreToolUse entries that register the model-routing dispatch hook."""
    return [
        entry
        for entry in hooks.get("PreToolUse", [])
        if "agent_model_resolve.py" in _script_names(entry)
    ]


def test_dispatch_matcher_covers_both_dispatch_tool_names() -> None:
    """The regression guard #1178 asked for: whichever name the harness
    uses for subagent dispatch ("Task" pre-2.1.63, "Agent" after), the
    routing hooks must fire."""
    for path in (HOOKS_JSON, SETTINGS_JSON):
        entries = _dispatch_entries(_load_hooks(path))
        assert entries, f"{path.name}: agent_model_resolve.py not registered"
        for entry in entries:
            matcher = entry["matcher"]
            for tool_name in DISPATCH_TOOL_NAMES:
                assert re.fullmatch(matcher, tool_name), (
                    f"{path.name}: PreToolUse matcher {matcher!r} does not "
                    f"match dispatch tool name {tool_name!r} — model "
                    f"routing would silently never fire (#1178)"
                )


def test_dispatch_entry_registers_both_dispatch_hooks() -> None:
    for path in (HOOKS_JSON, SETTINGS_JSON):
        entries = _dispatch_entries(_load_hooks(path))
        scripts = [s for entry in entries for s in _script_names(entry)]
        for script in DISPATCH_HOOK_SCRIPTS:
            assert script in scripts, (
                f"{path.name}: {script} missing from the subagent-dispatch "
                f"PreToolUse entry"
            )
