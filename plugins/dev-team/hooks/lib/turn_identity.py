"""turn_identity — shared transcript/turn identity helpers.

Extracted from the tail-window logic that used to live independently in
both `codegraph_nudge.py` (read side) and `codegraph_turn_mark.py` (write
side) — the latter's own docstring already flagged this exact duplication
as intended for a "future PR." Both hooks now import from here so the
transcript_id/turn_counter computation can't drift between the two sides
of the sentinel contract.

Stdlib-only. Python 3.8+.
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
