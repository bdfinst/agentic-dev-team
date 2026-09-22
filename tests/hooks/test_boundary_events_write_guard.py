"""End-to-end tests for hooks/boundary_events_write_guard.py (#2171).

Plan Step 1.1 covers the Write/Edit path-match guard. Plan Step 1.2 adds
Bash `tool_input.command` write-shape detection — covered below.

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

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "boundary_events_write_guard.py"

# Test-file-local constant (not `boundary_events_write_guard._LEDGER_NAME` —
# importing the code under test's own constant would make the test oracle
# circular against the code under test).
_LEDGER_REL_PATH = ".claude/metrics/boundary-events.jsonl"


def _run_raw(input_bytes: bytes) -> subprocess.CompletedProcess:
    """Lower-level subprocess wiring shared by every test here — `_run()`
    is the payload-shaped convenience wrapper; a test exercising a
    non-JSON/malformed stdin body calls this directly instead of
    hand-rolling its own `subprocess.run()`."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=input_bytes,
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _run(payload: dict) -> subprocess.CompletedProcess:
    return _run_raw(json.dumps(payload).encode())


def _read_jsonl(path: Path) -> list:
    if not path.is_file():
        return []
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def assert_boundary_event(
    event: dict,
    *,
    hook: str,
    tool: str,
    decision: str,
    matched_rule: str,
    session_id: str | None = None,
) -> None:
    """Shared assertion for a single recorded boundary-events row — used in
    place of the duplicated 5-field inline assertion block at each of this
    file's two "blocked and records its own event" tests."""
    assert event["hook"] == hook
    assert event["tool"] == tool
    assert event["decision"] == decision
    assert event["matched_rule"] == matched_rule
    if session_id is not None:
        assert event["session_id"] == session_id


def test_write_to_ledger_is_blocked_and_records_its_own_event(tmp_path: Path) -> None:
    ledger = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"

    result = _run(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": _LEDGER_REL_PATH,
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
    assert_boundary_event(
        events[0],
        hook="boundary_events_write_guard",
        tool="Write",
        decision="block",
        matched_rule="ledger-write-blocked",
        session_id="sess-1",
    )


def test_edit_to_ledger_is_blocked(tmp_path: Path) -> None:
    result = _run(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": _LEDGER_REL_PATH,
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
                "file_path": "./" + _LEDGER_REL_PATH,
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
    result = _run_raw(b"not json")
    assert result.returncode == 0
    assert result.stdout == b""


# ---------------------------------------------------------------------------
# Bash write-shaped commands (Step 1.2)
# ---------------------------------------------------------------------------


def test_bash_redirect_to_ledger_is_blocked_and_records_its_own_event(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"

    result = _run(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "echo '{}' >> " + _LEDGER_REL_PATH},
            "cwd": str(tmp_path),
            "session_id": "sess-2",
        }
    )

    assert result.returncode == 2
    assert b"BLOCKED" in result.stdout
    assert b"hooks/lib/boundary_events.py" in result.stdout
    # Message names the CLI's actual invocable shape — a flag-based
    # `--event` drawn from a closed vocabulary plus `--subject-hash`, not
    # the unusable positional form the message previously printed (review
    # finding, Step 1.2 correction).
    assert b"--event" in result.stdout
    assert b"--subject-hash" in result.stdout
    # Bash-path message names the CLI, not the Python-only function
    # (plan-review-ux finding, Step 1.2).
    assert b"emit_boundary_event()" not in result.stdout

    events = _read_jsonl(ledger)
    assert len(events) == 1
    assert_boundary_event(
        events[0],
        hook="boundary_events_write_guard",
        tool="Bash",
        decision="block",
        matched_rule="ledger-write-blocked",
        session_id="sess-2",
    )


def test_bash_heredoc_with_trailing_redirect_to_ledger_is_blocked(
    tmp_path: Path,
) -> None:
    result = _run(
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "cat <<'EOF' >> " + _LEDGER_REL_PATH + "\n"
                '{"forged": true}\n'
                "EOF"
            },
            "cwd": str(tmp_path),
        }
    )

    assert result.returncode == 2
    assert b"BLOCKED" in result.stdout


def test_bash_tee_to_ledger_is_blocked(tmp_path: Path) -> None:
    result = _run(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "echo '{}' | tee -a " + _LEDGER_REL_PATH},
            "cwd": str(tmp_path),
        }
    )

    assert result.returncode == 2


@pytest.mark.parametrize(
    "command",
    [
        # relative
        "echo '{}' >> " + _LEDGER_REL_PATH,
        # absolute (constructed per-test below instead, see next test)
        # "./"-prefixed
        "echo '{}' >> ./" + _LEDGER_REL_PATH,
        # bare filename after a `cd .claude/metrics`-shaped prefix
        "cd .claude/metrics && echo '{}' >> boundary-events.jsonl",
    ],
)
def test_bash_write_blocked_regardless_of_relative_path_form(
    tmp_path: Path, command: str
) -> None:
    result = _run(
        {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(tmp_path),
        }
    )

    assert result.returncode == 2


def test_bash_write_blocked_for_absolute_path_form(tmp_path: Path) -> None:
    absolute = str(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    result = _run(
        {
            "tool_name": "Bash",
            "tool_input": {"command": f"echo '{{}}' >> {absolute}"},
            "cwd": str(tmp_path),
        }
    )

    assert result.returncode == 2


@pytest.mark.parametrize(
    "command",
    [
        "tail -20 " + _LEDGER_REL_PATH,
        "cat " + _LEDGER_REL_PATH,
        "grep foo " + _LEDGER_REL_PATH,
        "python3 -c \"print(open('" + _LEDGER_REL_PATH + "').read())\"",
    ],
)
def test_bash_reads_of_ledger_are_allowed(tmp_path: Path, command: str) -> None:
    result = _run(
        {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(tmp_path),
        }
    )

    assert result.returncode == 0
    assert result.stdout == b""
    assert not (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").exists()


def test_bash_write_to_unrelated_file_is_allowed(tmp_path: Path) -> None:
    result = _run(
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "echo '{}' >> .claude/metrics/session-digest.jsonl"
            },
            "cwd": str(tmp_path),
        }
    )

    assert result.returncode == 0
    assert result.stdout == b""
