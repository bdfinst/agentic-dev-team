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

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import destructive_guard  # type: ignore[import-not-found]  # noqa: E402


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
