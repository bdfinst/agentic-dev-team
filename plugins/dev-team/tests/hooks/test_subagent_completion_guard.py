"""Tests for hooks/subagent_completion_guard.py's classify_stop() (#2188).

Fixture transcripts cover each of Step 2.1b's confirmed scenarios plus the
two precedence edge cases the plan calls out explicitly: the max_tokens +
empty-content overlap, and a structurally-malformed (not just empty) last
row.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parents[2] / "hooks"
_HOOK_PY = _HOOK_DIR / "subagent_completion_guard.py"
if str(_HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOK_DIR))

from subagent_completion_guard import classify_stop


def _write_transcript(tmp_path: Path, rows: list[dict], name: str = "transcript.jsonl") -> str:
    path = tmp_path / name
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return str(path)


def _assistant_row(content, stop_reason=None) -> dict:
    return {
        "type": "assistant",
        "isSidechain": True,
        "message": {
            "role": "assistant",
            "content": content,
            "stop_reason": stop_reason,
        },
    }


def test_clean_completion_with_null_stop_reason(tmp_path):
    """Finding 2: null stop_reason is the common (87%) clean case, not an edge case."""
    path = _write_transcript(
        tmp_path, [_assistant_row([{"type": "text", "text": "Report delivered."}], None)]
    )
    assert classify_stop(path) == "clean"


def test_clean_completion_with_end_turn_stop_reason(tmp_path):
    path = _write_transcript(
        tmp_path,
        [_assistant_row([{"type": "text", "text": "Done."}], "end_turn")],
    )
    assert classify_stop(path) == "clean"


def test_empty_final_turn(tmp_path):
    path = _write_transcript(
        tmp_path, [_assistant_row([{"type": "text", "text": "   "}], None)]
    )
    assert classify_stop(path) == "empty-final-turn"


def test_empty_final_turn_with_empty_content_list(tmp_path):
    path = _write_transcript(tmp_path, [_assistant_row([], "end_turn")])
    assert classify_stop(path) == "empty-final-turn"


def test_truncated_final_turn(tmp_path):
    path = _write_transcript(
        tmp_path,
        [_assistant_row([{"type": "text", "text": "partial output..."}], "max_tokens")],
    )
    assert classify_stop(path) == "truncated-final-turn"


def test_max_tokens_and_empty_content_overlap_prefers_truncated(tmp_path):
    """Precedence rule 2 beats rule 3: max_tokens wins even with empty content."""
    path = _write_transcript(tmp_path, [_assistant_row([], "max_tokens")])
    assert classify_stop(path) == "truncated-final-turn"


def test_structurally_malformed_last_row_fails_open(tmp_path):
    """Last row is valid JSON but missing message/content entirely — distinct
    from an unreadable file, still fails open."""
    path = _write_transcript(tmp_path, [{"type": "assistant", "isSidechain": True}])
    assert classify_stop(path) == "unreadable"


def test_missing_transcript_file_fails_open(tmp_path):
    path = str(tmp_path / "does-not-exist.jsonl")
    assert classify_stop(path) == "unreadable"


def test_transcript_with_only_blank_lines_fails_open(tmp_path):
    path = tmp_path / "blank.jsonl"
    path.write_text("\n\n\n", encoding="utf-8")
    assert classify_stop(str(path)) == "unreadable"


def test_last_row_is_invalid_json_fails_open(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"valid": true}\nnot json at all\n', encoding="utf-8")
    assert classify_stop(str(path)) == "unreadable"


def test_earlier_rows_ignored_only_last_row_governs(tmp_path):
    """A truncated earlier turn followed by a clean final turn classifies clean."""
    path = _write_transcript(
        tmp_path,
        [
            _assistant_row([{"type": "text", "text": "partial"}], "max_tokens"),
            _assistant_row([{"type": "text", "text": "Report delivered."}], None),
        ],
    )
    assert classify_stop(path) == "clean"


# ---------------------------------------------------------------------------
# main() end-to-end + boundary-events emission (#2188 Step 2.2).
# ---------------------------------------------------------------------------


def _events_path(tmp_path: Path) -> Path:
    return tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"


def _run_hook(raw_stdin: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=raw_stdin,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True,
        timeout=10,
        check=False,
    )


def _run_main(tmp_path, transcript_path: str) -> int:
    """Invoke the real script end-to-end via subprocess — exercises `main()`'s
    actual stdin-parsing path (`read_stdin_json`) instead of monkeypatching
    that internal collaborator, matching
    `test_subagent_skill_context.py`'s `_run_hook()` convention."""
    payload = {
        "transcript_path": transcript_path,
        "session_id": "sess-1",
        "cwd": str(tmp_path),
    }
    result = _run_hook(json.dumps(payload).encode())
    assert result.stdout == b""
    assert result.stderr == b""
    return result.returncode


def test_main_emits_nothing_for_clean_transcript(tmp_path):
    transcript = _write_transcript(
        tmp_path, [_assistant_row([{"type": "text", "text": "Report delivered."}], None)]
    )
    assert _run_main(tmp_path, transcript) == 0
    assert not _events_path(tmp_path).exists()


def test_main_emits_empty_final_turn_event(tmp_path):
    transcript = _write_transcript(tmp_path, [_assistant_row([], "end_turn")])
    assert _run_main(tmp_path, transcript) == 0

    events_path = _events_path(tmp_path)
    assert events_path.is_file()
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line]
    assert len(events) == 1
    assert events[0]["hook"] == "subagent_completion_guard"
    assert events[0]["tool"] == "SubagentStop"
    assert events[0]["decision"] == "warn"
    assert events[0]["matched_rule"] == "empty-final-turn"
    assert events[0]["session_id"] == "sess-1"


def test_main_emits_truncated_final_turn_event(tmp_path):
    transcript = _write_transcript(
        tmp_path,
        [_assistant_row([{"type": "text", "text": "partial..."}], "max_tokens")],
    )
    assert _run_main(tmp_path, transcript) == 0

    events_path = _events_path(tmp_path)
    assert events_path.is_file()
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line]
    assert len(events) == 1
    assert events[0]["matched_rule"] == "truncated-final-turn"


def test_main_emits_nothing_for_unreadable_transcript(tmp_path):
    missing = str(tmp_path / "does-not-exist.jsonl")
    assert _run_main(tmp_path, missing) == 0
    assert not _events_path(tmp_path).exists()


def test_main_is_silent_pass_on_malformed_stdin() -> None:
    """Drives `main()`'s real `read_stdin_json()` call through invalid JSON —
    the fail-open contract the module docstring claims ("Any error -> exit 0
    silently"), previously exercised only via `classify_stop()` directly."""
    result = _run_hook(b"not json")
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""


def test_main_is_silent_pass_on_missing_transcript_path_key() -> None:
    result = _run_hook(json.dumps({"session_id": "sess-1", "cwd": "/tmp"}).encode())
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
