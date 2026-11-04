"""Verify key hooks are registered at the right lifecycle points in
settings.json.

Ported from tests/hooks/settings_registration_test.bats (issue #676).
"""

from __future__ import annotations

import json
import re

from _repo_root import REPO_ROOT

SETTINGS = REPO_ROOT / "plugins" / "dev-team" / "settings.json"
HOOKS_JSON = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "hooks.json"


def _load() -> dict:
    return json.loads(SETTINGS.read_text())


def _commands(entries) -> list[str]:
    commands = []
    for entry in entries:
        for hook in entry.get("hooks", []):
            commands.append(hook.get("command", ""))
    return commands


def test_settings_json_is_valid_json() -> None:
    _load()  # raises if invalid


def test_mutation_gate_py_is_registered_in_post_tool_use_bash_hooks() -> None:
    data = _load()
    bash_entries = [
        entry
        for entry in data["hooks"]["PostToolUse"]
        if entry.get("matcher") == "Bash"
    ]
    commands = _commands(bash_entries)
    assert any("mutation_gate.py" in cmd for cmd in commands)


def test_mutation_gate_is_in_post_tool_use_not_pre_tool_use() -> None:
    data = _load()
    commands = _commands(data["hooks"].get("PreToolUse", []))
    assert not any("mutation_gate.py" in cmd for cmd in commands)


def test_session_learning_trigger_py_is_registered_in_session_end_hooks() -> None:
    data = _load()
    commands = _commands(data["hooks"]["SessionEnd"])
    assert any("session_learning_trigger.py" in cmd for cmd in commands)


def test_verify_guard_py_is_registered_in_pre_tool_use_bash_hooks() -> None:
    data = _load()
    bash_entries = [
        entry for entry in data["hooks"]["PreToolUse"] if entry.get("matcher") == "Bash"
    ]
    commands = _commands(bash_entries)
    assert any("verify_guard.py" in cmd for cmd in commands)


def test_verify_guard_edit_marker_py_is_registered_on_write_edit_notebookedit() -> None:
    """#708: verify_guard.py's edit-since-last-verify signal is written by
    this sibling hook, which must be wired to the tool matcher that covers
    Edit, Write, AND NotebookEdit — not just the narrower Write|Edit matcher
    used by the pre_tool_guard.py / contract_version_guard.py pair."""
    data = _load()
    entries = [
        entry
        for entry in data["hooks"]["PreToolUse"]
        if entry.get("matcher") == "Write|Edit|NotebookEdit"
    ]
    commands = _commands(entries)
    assert any("verify_guard_edit_marker.py" in cmd for cmd in commands)


def _registrations(path, script: str) -> list[tuple[str, str, list[str]]]:
    """Every `(event, matcher, [script basenames in the group])` whose group
    runs `script`, one tuple per registration."""
    found = []
    for event, entries in json.loads(path.read_text())["hooks"].items():
        for entry in entries:
            names = [
                re.findall(r"([A-Za-z0-9_]+\.py)", hook["command"])[-1]
                for hook in entry.get("hooks", [])
            ]
            found += [
                (event, entry.get("matcher", ""), names) for n in names if n == script
            ]
    return found


def test_feature_record_guard_is_registered_once_in_each_file_in_matching_shape() -> (
    None
):
    """#2275: the write guard sits in the Write|Edit PreToolUse group of both
    hooks.json (the file current Claude Code loads) and settings.json (the
    older-CLI mirror), once each, beside the same neighbours."""
    script = "feature_record_guard.py"
    in_hooks_json = _registrations(HOOKS_JSON, script)
    in_settings = _registrations(SETTINGS, script)
    assert len(in_hooks_json) == 1, in_hooks_json
    assert len(in_settings) == 1, in_settings
    assert in_hooks_json == in_settings
    event, matcher, group = in_hooks_json[0]
    assert (event, matcher) == ("PreToolUse", "Write|Edit")
    assert group.count(script) == 1
