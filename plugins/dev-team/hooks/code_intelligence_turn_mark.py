#!/usr/bin/env python3
"""Renamed/generalized from codegraph_turn_mark.py (#594 / #572 Phase 3, #1368).

Claude Code PostToolUse hook. Fires after a tool call completes and
`_tool_family()` recognizes its name as belonging to a supported
code-intelligence tool family — currently `mcp__codegraph__*` ("codegraph")
and `mcp__plugin_repowise_repowise__*` ("repowise"). Writes a sentinel at
`${CLAUDE_PROJECT_DIR:-$PWD}/.claude/codegraph-turn-state.json` that the nudge
hook (`code_intelligence_nudge.py`) consults to suppress its warning for
whichever tool family was used during the rest of the current turn.

`_transcript_id`/`_count_user_lines` are imported from the shared
`hooks/lib/turn_identity.py` module (falling back to local reimplementations
only if that import fails) so this hook and the nudge hook can never drift
apart on how a "turn" is identified.

Sentinel schema (unchanged in this step — Step 2.2 upgrades it to an
accumulating `tools_used` list; for now the write-path stays codegraph-only,
recognizing but not yet acting on the "repowise" family `_tool_family` can
return):
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

Stdlib-only (json/os/pathlib/sys/tempfile). Python 3.8+. See ADR 0014.

Refs: #572 (bash → Python migration epic), #1368 (multi-tool nudge).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from turn_identity import (  # type: ignore[import-not-found]
        count_user_lines as _count_user_lines,
        transcript_id as _transcript_id,
    )
except ImportError:  # pragma: no cover

    def _transcript_id(path: str) -> str:  # type: ignore[misc]
        return Path(path).stem

    def _count_user_lines(transcript_path: Path) -> int:  # type: ignore[misc]
        return 0


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


def _tool_family(name: str) -> str | None:
    """Classify a tool name into the family whose usage this hook marks.

    Same prefix filter the .sh applied via
    `case "$TOOL_NAME" in mcp__codegraph__*)`, generalized to also recognize
    Repowise's MCP server prefix. Any other tool name (or a name matching
    neither prefix) returns None.
    """
    if name.startswith("mcp__codegraph__"):
        return "codegraph"
    if name.startswith("mcp__plugin_repowise_repowise__"):
        return "repowise"
    return None


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
    # Step 2.2/2.3 will widen this to accumulate every recognized family into
    # the sentinel's tools_used list; for now the sentinel schema/write-path
    # stays codegraph-only, matching the behavior preserved from before this
    # rename (see plans/multi-tool-code-intelligence-nudge.md Step 2.1).
    if not isinstance(tool_name, str) or _tool_family(tool_name) != "codegraph":
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
