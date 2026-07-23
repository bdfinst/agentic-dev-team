#!/usr/bin/env python3
"""Renamed/generalized from codegraph_turn_mark.py (#594 / #572 Phase 3, #1368).

Claude Code PostToolUse hook. Fires after a tool call completes and
`_tool_family()` recognizes its name as belonging to a supported
code-intelligence tool family — currently `mcp__codegraph__*` ("codegraph")
and `mcp__plugin_repowise_repowise__*` ("repowise"). Writes a sentinel at
`${CLAUDE_PROJECT_DIR:-$PWD}/.claude/code-intelligence-turn-state.json` that
the nudge hook (`code_intelligence_nudge.py`) will consult (Step 2.3) to
suppress its warning for whichever tool family was used during the rest of
the current turn.

`transcript_id`/`count_user_lines` are imported from the shared
`hooks/lib/turn_identity.py` module (falling back to local reimplementations
only if that import fails) so this hook and the nudge hook can never drift
apart on how a "turn" is identified. The same module's `matches_current_turn`
owns the identity-match predicate for both this hook's read-modify-write
merge and the nudge hook's read-side suppression check.

Sentinel schema (Step 2.2 — accumulating `tools_used` list, written to
`.claude/code-intelligence-turn-state.json`):
    { "transcript_id": <string>, "turn_counter": <int>, "tools_used": [<string>, ...] }
    - transcript_id: basename of transcript_path with extension stripped
    - turn_counter:  count of `"type":"user"` lines in the transcript file,
                     scanning only the last 1 MiB so a monotonically growing
                     transcript stays O(1) per fire (same cap the nudge hook
                     applies on its side).
    - tools_used:    families (e.g. "codegraph", "repowise") recognized so
                     far this turn, in first-used order, deduplicated.

Before writing, any existing sentinel is read back. When its transcript_id
and turn_counter match the freshly computed values (same turn), the newly
recognized family is merged into the existing `tools_used` list (deduped,
order preserved); otherwise — new turn, new transcript, or a
missing/legacy/corrupt sentinel — the sentinel is rewritten from scratch
with only the new family. A `tools_used` field that exists but isn't a
list, or a sentinel that fails to parse at all, is treated as an empty list
rather than raised (fail-open on the write side, mirroring the nudge hook's
read-side handling of the same shapes).

Both `transcript_id`/`turn_counter` are computed the same way the nudge hook
recomputes them at PreToolUse time, so a same-turn match accumulates and a
next-turn mismatch (new user message → counter bumps) resets it.

Contract (docs/python-hook-contract.md):
    Input : PostToolUse JSON on stdin
    Output: writes sentinel file; no stdout. Exit 0.
    Posture: fail-open. Any internal error → exit 0; sentinel may not be
             written, the nudge hook will simply emit its (advisory) warning.

Stdlib-only (json/os/pathlib/sys/tempfile). Python 3.8+. See ADR 0014.

Refs: #572 (bash → Python migration epic), #1368 (multi-tool nudge).
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

try:
    import fcntl  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — Windows has no fcntl
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — POSIX has no msvcrt
    msvcrt = None  # type: ignore[assignment]

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from turn_identity import (  # type: ignore[import-not-found]
        SENTINEL_RELATIVE_PATH,
        count_user_lines,
        matches_current_turn,
        transcript_id,
    )
except ImportError:  # pragma: no cover

    SENTINEL_RELATIVE_PATH = Path(".claude") / "code-intelligence-turn-state.json"  # type: ignore[misc]

    def transcript_id(path: str) -> str:  # type: ignore[misc]
        return Path(path).stem

    def count_user_lines(transcript_path: Path) -> int:  # type: ignore[misc]
        return 0

    def matches_current_turn(sentinel: dict, tid: str, tc: int) -> bool:  # type: ignore[misc]
        sentinel_tid = str(sentinel.get("transcript_id") or "")
        if sentinel_tid != tid:
            return False
        try:
            return int(sentinel.get("turn_counter")) == tc
        except (TypeError, ValueError):
            return False


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


def _existing_tools_used(sentinel: Path, tid: str, tc: int) -> list:
    """Read back any prior sentinel's `tools_used` for the current turn.

    Fail-open on every corrupt/legacy shape — an unreadable file, invalid
    JSON, a non-dict payload, a mismatched transcript/turn (new turn), a
    missing `tools_used` field (legacy pre-Slice-2 schema), or a
    `tools_used` present but not a list — all resolve to "start fresh",
    i.e. an empty list, never a raised exception. The same-turn check
    itself is `turn_identity.matches_current_turn` — the single predicate
    shared with the nudge hook's read side, so the two sides of the
    sentinel contract can't drift on turn-counter coercion.
    """
    if not sentinel.is_file():
        return []
    try:
        existing = json.loads(sentinel.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    if not isinstance(existing, dict):
        return []
    if not matches_current_turn(existing, tid, tc):
        return []
    tools_used = existing.get("tools_used")
    if not isinstance(tools_used, list):
        return []
    return tools_used


def _merge_tools_used(existing: list, family: str) -> list:
    """Append `family` to `existing`, deduped, preserving first-seen order."""
    if family in existing:
        return list(existing)
    return list(existing) + [family]


def _test_delay() -> None:
    """Test-only injection point: sleep inside the locked read-merge-write
    section when `CODE_INTELLIGENCE_TURN_MARK_TEST_DELAY_MS` is set,
    widening the race window so a concurrency test can deterministically
    force two hook invocations to overlap on the same sentinel rather than
    relying on real-world timing luck. Unset in production; a bad/missing
    value is a no-op (fail-open)."""
    delay_ms = os.environ.get("CODE_INTELLIGENCE_TURN_MARK_TEST_DELAY_MS")
    if not delay_ms:
        return
    try:
        time.sleep(int(delay_ms) / 1000)
    except (ValueError, OSError):
        pass


@contextlib.contextmanager
def _sentinel_lock(sentinel: Path):
    """Exclusive advisory lock held for the full read-merge-write cycle.

    Prevents the lost-update race where two concurrent PostToolUse
    invocations (e.g. two MCP tool calls firing in quick succession) both
    read the same stale `tools_used` list, merge in different families, and
    one write clobbers the other's update. `fcntl.flock` on POSIX,
    `msvcrt.locking` on Windows (this repo's hooks target both — see the
    Windows note on `_write_sentinel_atomic`'s tempfile+rename above).

    Fail-open: any failure to open/lock the lock file — missing `fcntl` and
    `msvcrt` both, or an `OSError` opening it — falls through to running the
    critical section unlocked rather than raising. A lost-update race under
    that fallback is strictly worse than today's behavior (already racy)
    but a crash is not; this hook is a nudge dependency, never a gate.
    """
    lock_path = sentinel.parent / (sentinel.name + ".lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock_path, "a+")
    except OSError:
        yield
        return

    locked = False
    try:
        try:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                locked = True
            elif msvcrt is not None:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                locked = True
        except OSError:
            locked = False
        yield
    finally:
        if locked:
            try:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                elif msvcrt is not None:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        fh.close()


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
            prefix=".code-intelligence-turn-state.",
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
    family = _tool_family(tool_name) if isinstance(tool_name, str) else None
    if family is None:
        return 0

    transcript_path_str = payload.get("transcript_path") or ""
    if not isinstance(transcript_path_str, str) or not transcript_path_str:
        return 0
    transcript_path = Path(transcript_path_str)
    if not transcript_path.is_file():
        return 0

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    sentinel = project_dir / SENTINEL_RELATIVE_PATH

    tid = transcript_id(transcript_path_str)
    tc = count_user_lines(transcript_path)

    with _sentinel_lock(sentinel):
        tools_used = _merge_tools_used(_existing_tools_used(sentinel, tid, tc), family)
        _test_delay()
        _write_sentinel_atomic(
            sentinel,
            {"transcript_id": tid, "turn_counter": tc, "tools_used": tools_used},
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open on any unexpected error — matches the module docstring's
        # posture ("Any internal error -> exit 0") and the sibling nudge
        # hook's identical guard.
        sys.exit(0)
