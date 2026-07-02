#!/usr/bin/env python3
"""Python port of hooks/codegraph-turn-mark.sh (#594 / #572 Phase 3).

Byte-compatible port of the Claude Code PostToolUse hook. Fires after any
`mcp__codegraph__*` tool call completes. Writes a sentinel at
`${CLAUDE_PROJECT_DIR:-$PWD}/.claude/codegraph-turn-state.json` that the nudge
hook (`codegraph-nudge.sh`) consults to suppress its warning during the rest
of the current turn.

Sentinel schema (same as the .sh):
    { "transcript_id": <string>, "turn_counter": <int> }
    - transcript_id: basename of transcript_path with extension stripped
    - turn_counter:  count of `"type":"user"` lines in the transcript file,
                     scanning only the last 1 MiB so a monotonically growing
                     transcript stays O(1) per fire (same cap the nudge hook
                     applies on its side).

Both fields are computed the same way the nudge hook recomputes them at
PreToolUse time, so a same-turn match suppresses the warning and a next-turn
mismatch (new user message → counter bumps) resets it.

Contract (docs/python-hook-contract.md):
    Input : PostToolUse JSON on stdin
    Output: writes sentinel file; no stdout. Exit 0.
    Posture: fail-open. Any internal error → exit 0; sentinel may not be
             written, the nudge hook will simply emit its (advisory) warning.

Stdlib-only (json/os/pathlib/re/sys/tempfile). Python 3.8+. See ADR 0014.

Refs: #572 (bash → Python migration epic).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path


# Same 1 MiB tail window the .sh applies via `tail -c 1048576`. Kept as a
# module-level constant so the nudge-hook port (future PR) can import it
# instead of re-declaring the magic number.
_TAIL_WINDOW_BYTES = 1_048_576

# Matches the .sh's `grep -c '"type":"user"'` — literal substring, no JSON
# parsing. Transcripts are JSONL and the marker is stable across all
# assistant/user records the harness writes.
_USER_LINE_RE = re.compile(rb'"type":"user"')


def _read_stdin() -> str:
    """Read the stdin payload once. Empty on error — the .sh silently exits 0."""
    try:
        return sys.stdin.read()
    except (OSError, ValueError):
        return ""


def _load_input(raw: str) -> dict:
    """Parse the PostToolUse JSON. Malformed input → {} (fail-open)."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_codegraph_tool(name: str) -> bool:
    # Same prefix filter as the .sh's `case "$TOOL_NAME" in mcp__codegraph__*)`.
    return name.startswith("mcp__codegraph__")


def _transcript_id(transcript_path: str) -> str:
    """basename(transcript_path) with the last extension stripped.

    Mirrors the .sh's two-step:
        TRANSCRIPT_ID=$(basename "$TRANSCRIPT_PATH")
        TRANSCRIPT_ID="${TRANSCRIPT_ID%.*}"

    `${var%.*}` removes the shortest suffix matching `.*`, i.e. the final
    extension only. `Path.stem` matches that behavior for the shapes the
    harness emits (`.jsonl`, `.json`, no extension).
    """
    return Path(transcript_path).stem


def _count_user_lines(transcript_path: Path) -> int:
    """Count `"type":"user"` occurrences in the last 1 MiB of the transcript.

    Errors → 0 (fail-open, matches the .sh's `|| echo 0`). Reads a bounded
    tail so growing transcripts don't turn every codegraph call into a
    full-file scan.
    """
    try:
        with transcript_path.open("rb") as fh:
            try:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                offset = max(0, size - _TAIL_WINDOW_BYTES)
                fh.seek(offset)
            except (OSError, ValueError):
                # Non-seekable? Read from the top; small transcripts stay cheap.
                fh.seek(0)
            data = fh.read()
    except OSError:
        return 0
    return len(_USER_LINE_RE.findall(data))


def _write_sentinel_atomic(sentinel: Path, payload: dict) -> None:
    """Atomic write via a tempfile in the same directory + rename.

    Mirrors the .sh's `mktemp` + `mv -f` pattern so the nudge hook never sees
    a partial JSON. Any failure short-circuits to a silent exit 0.
    """
    parent = sentinel.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    # NamedTemporaryFile with delete=False + explicit rename gives us the
    # same atomic-mv semantic on macOS + Linux + Windows Git Bash.
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=".codegraph-turn-state.",
            dir=str(parent),
        )
    except OSError:
        return
    tmp = Path(tmp_path)
    try:
        # jq -n produces two-space-indented pretty JSON with a trailing
        # newline. Match that byte-for-byte: `json.dumps(..., indent=2)` uses
        # ": " (space after colon) and "," between items — the exact shape jq
        # emits — and we append the trailing `\n` jq always writes.
        body = json.dumps(payload, indent=2)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
            fh.write("\n")
        os.replace(tmp, sentinel)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def main() -> int:
    raw = _read_stdin()
    if not raw:
        return 0

    payload = _load_input(raw)
    tool_name = payload.get("tool_name") or ""
    if not isinstance(tool_name, str) or not _is_codegraph_tool(tool_name):
        return 0

    transcript_path_str = payload.get("transcript_path") or ""
    if not isinstance(transcript_path_str, str) or not transcript_path_str:
        return 0
    transcript_path = Path(transcript_path_str)
    if not transcript_path.is_file():
        return 0

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    sentinel = project_dir / ".claude" / "codegraph-turn-state.json"

    tid = _transcript_id(transcript_path_str)
    tc = _count_user_lines(transcript_path)

    _write_sentinel_atomic(sentinel, {"transcript_id": tid, "turn_counter": tc})
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
