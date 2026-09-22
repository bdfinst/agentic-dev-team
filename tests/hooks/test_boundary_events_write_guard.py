"""End-to-end tests for hooks/boundary_events_write_guard.py (#2171, plan
Step 1.1 — Write/Edit path-match guard only; Bash write-shaped command
detection and settings.json registration are Step 1.2, not covered here).

Drives main() via subprocess with representative PreToolUse JSON payloads,
using the real `emit_boundary_event()` write path (mirrors
tests/hooks/test_agent_dispatch_ledger.py) — confirms the guard both blocks
AND allows for real, and that a block leaves its own boundary-events trace
(plan Step 1.1 IMPLEMENT note: "every sibling guard ... records its own
decision"). Unit-level coverage of the guard's internals lives in
plugins/dev-team/tests/hooks/test_boundary_events_write_guard.py (matches
tests/hooks/test_destructive_guard.py's own e2e-vs-unit split).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "boundary_events_write_guard.py"


def _run(payload: dict) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=json.dumps(payload).encode(),
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _read_jsonl(path: Path) -> list:
    if not path.is_file():
        return []
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def test_write_to_ledger_is_blocked_and_records_its_own_event(tmp_path: Path) -> None:
    ledger = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"

    result = _run(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".claude/metrics/boundary-events.jsonl",
                "content": '{"forged": true}\n',
            },
            "cwd": str(tmp_path),
            "session_id": "sess-1",
        }
    )

    assert result.returncode == 2
    assert b"BLOCKED" in result.stdout
    assert b"emit_boundary_event()" in result.stdout

    events = _read_jsonl(ledger)
    assert len(events) == 1
    event = events[0]
    assert event["hook"] == "boundary_events_write_guard"
    assert event["tool"] == "Write"
    assert event["decision"] == "block"
    assert event["matched_rule"] == "ledger-write-blocked"
    assert event["session_id"] == "sess-1"


def test_edit_to_ledger_is_blocked(tmp_path: Path) -> None:
    result = _run(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": ".claude/metrics/boundary-events.jsonl",
                "old_string": "a",
                "new_string": "b",
            },
            "cwd": str(tmp_path),
        }
    )

    assert result.returncode == 2
    assert b"emit_boundary_event()" in result.stdout


def test_write_to_unrelated_file_is_allowed_and_records_nothing(tmp_path: Path) -> None:
    result = _run(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "README.md", "content": "hello\n"},
            "cwd": str(tmp_path),
        }
    )

    assert result.returncode == 0
    assert result.stdout == b""
    assert not (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").exists()


def test_write_to_review_verdicts_store_is_allowed(tmp_path: Path) -> None:
    """Slice 2's own store (#2166) — not affected by this guard, which
    matches the exact ledger name/path, not a `.claude/metrics/` prefix."""
    result = _run(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".claude/metrics/review-verdicts.jsonl",
                "content": "{}\n",
            },
            "cwd": str(tmp_path),
        }
    )

    assert result.returncode == 0
    assert result.stdout == b""


def test_absolute_path_to_ledger_is_blocked(tmp_path: Path) -> None:
    absolute = str(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    result = _run(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": absolute, "content": "{}\n"},
            "cwd": str(tmp_path),
        }
    )

    assert result.returncode == 2


def test_dot_slash_prefixed_path_to_ledger_is_blocked(tmp_path: Path) -> None:
    result = _run(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "./.claude/metrics/boundary-events.jsonl",
                "content": "{}\n",
            },
            "cwd": str(tmp_path),
        }
    )

    assert result.returncode == 2


def test_missing_tool_input_is_silent_pass(tmp_path: Path) -> None:
    result = _run({"tool_name": "Write", "cwd": str(tmp_path)})
    assert result.returncode == 0
    assert result.stdout == b""


def test_malformed_stdin_is_silent_pass() -> None:
    result = subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=b"not json",
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == b""
