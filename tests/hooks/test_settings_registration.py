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


def _registrations(path, script: str) -> list[tuple[str, str]]:
    """Every `(event, matcher)` of a group that runs `script`, one tuple per
    registration. Hooks without a `.py` token in their command are skipped."""
    found = []
    for event, entries in json.loads(path.read_text())["hooks"].items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                scripts = re.findall(r"([A-Za-z0-9_]+\.py)", hook.get("command", ""))
                if scripts and scripts[-1] == script:
                    found.append((event, entry.get("matcher", "")))
    return found


def test_feature_record_guard_is_registered_once_in_each_file() -> None:
    """#2275: the write guard sits in the Write|Edit PreToolUse group of both
    hooks.json (the file current Claude Code loads) and settings.json (the
    older-CLI mirror), once each."""
    for path in (HOOKS_JSON, SETTINGS):
        assert _registrations(path, "feature_record_guard.py") == [
            ("PreToolUse", "Write|Edit")
        ], path
