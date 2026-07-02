"""Verify key hooks are registered at the right lifecycle points in
settings.json.

Ported from tests/hooks/settings_registration_test.bats (issue #676).
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS = REPO_ROOT / "plugins" / "dev-team" / "settings.json"


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


def test_session_learning_trigger_py_is_registered_in_session_stop_hooks() -> None:
    data = _load()
    commands = _commands(data["hooks"]["SessionStop"])
    assert any("session_learning_trigger.py" in cmd for cmd in commands)
