"""Tests for hooks/subagent_completion_guard.py's classify_stop() (#2188).

Fixture transcripts cover each of Step 2.1b's confirmed scenarios plus the
two precedence edge cases the plan calls out explicitly: the max_tokens +
empty-content overlap, and a structurally-malformed (not just empty) last
row.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parents[2] / "hooks"
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
