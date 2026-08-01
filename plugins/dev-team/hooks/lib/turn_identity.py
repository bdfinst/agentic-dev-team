"""turn_identity — shared transcript/turn identity helpers.

Extracted from the tail-window logic that used to live independently in
both `codegraph_nudge.py` (read side) and `codegraph_turn_mark.py` (write
side) — the latter's own docstring already flagged this exact duplication
as intended for a "future PR." Both hooks now import from here so the
transcript_id/turn_counter computation can't drift between the two sides
of the sentinel contract.

Stdlib-only.
"""

from __future__ import annotations

import os
from pathlib import Path

# Same 1 MiB tail window both hooks applied independently before this
# extraction — a monotonically growing transcript stays O(1) per read.
_TAIL_WINDOW_BYTES = 1_048_576

_USER_LINE_MARKER = b'"type":"user"'


def transcript_id(path: str) -> str:
    """basename(path) with the last extension stripped.

    `Path.stem` matches the shapes the harness emits (`.jsonl`, `.json`,
    no extension).
    """
    return Path(path).stem


def count_user_lines(transcript_path: Path) -> int:
    """Count `"type":"user"` occurrences in the last 1 MiB of the transcript.

    Errors -> 0 (fail-open). Reads a bounded tail so growing transcripts
    don't turn every call into a full-file scan.
    """
    try:
        with transcript_path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            offset = max(0, size - _TAIL_WINDOW_BYTES)
            fh.seek(offset, os.SEEK_SET)
            tail = fh.read()
    except OSError:
        return 0
    return tail.count(_USER_LINE_MARKER)


# Single source of truth for the sentinel's location relative to the
# project dir — both code_intelligence_nudge.py (read side) and
# code_intelligence_turn_mark.py (write side) used to hardcode this
# path independently.
SENTINEL_RELATIVE_PATH = Path(".claude") / "code-intelligence-turn-state.json"


def matches_current_turn(sentinel: dict, tid: str, tc: int) -> bool:
    """True when `sentinel`'s identity fields match the freshly computed
    transcript_id/turn_counter for the current call — i.e. the sentinel was
    written earlier in the *same* turn.

    Owns the type coercion once for both sides of the sentinel contract:
    `transcript_id` is compared as a string (coercing a missing/`None`
    value to `""`), and `turn_counter` is compared via `int()` wrapped in a
    try/except — a non-numeric or otherwise uncoercible value (corrupt
    sentinel) resolves to `False` rather than raising, matching this
    module's fail-open posture.
    """
    sentinel_tid = str(sentinel.get("transcript_id") or "")
    if sentinel_tid != tid:
        return False
    try:
        return int(sentinel.get("turn_counter")) == tc
    except (TypeError, ValueError):
        return False
