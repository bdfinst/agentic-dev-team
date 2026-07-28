#!/usr/bin/env python3
"""bash_retry_guard — Claude Code PreToolUse hook (Python port of bash-retry-guard.sh).

Detects repeated identical Bash commands within a session. After THRESHOLD
consecutive identical commands, nudges the agent to vary its approach
rather than re-running the same failing command.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin
    Output: advisory nudge on stdout when threshold reached
    Exit  : always 0 (advisory — never blocks)
    Env   : DEV_TEAM_BASH_RETRY_THRESHOLD (default 3; 0 disables)

State is persisted per-session under $TMPDIR/dev-team-bash-retry/<key>.json
where <key> is the session_id when present, else a cksum of $cwd. Files
are tiny and short-lived — no cleanup story needed beyond the OS's tmp
sweeping.

Stdlib-only. Python 3.8+. See #591 / #572 Phase 3.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from atomic_state import (  # type: ignore[import-not-found]
        atomic_write,
        locked_state,
        race_window_delay,
    )
    from boundary_events import (  # type: ignore[import-not-found]
        emit_boundary_event as _emit_boundary_event,
    )
    from stdin_json import read_stdin_json  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    import contextlib as _contextlib

    def read_stdin_json() -> dict | None:  # type: ignore[misc]
        return None

    def _emit_boundary_event(*_args, **_kwargs) -> None:  # type: ignore[misc]
        return None

    def atomic_write(path: Path, text: str) -> None:  # type: ignore[misc]
        try:
            path.write_text(text, encoding="utf-8")
        except OSError:
            pass

    @_contextlib.contextmanager
    def locked_state(_path: Path):  # type: ignore[misc]
        yield

    def race_window_delay(_env_var: str) -> None:  # type: ignore[misc]
        return None


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


# Verify-family commands — the verify-guard hook handles retry-nudging for
# these; this hook must not double-warn. The pattern MUST match the .sh's
# ERE byte-for-byte.
_VERIFY_RE = re.compile(
    r"\b(npm (run )?(test|lint|build)|pytest|bats|eslint|tsc|"
    r"go test|cargo (test|build)|mvn|gradle|make( |$)|vitest|"
    r"jest|ruff|mypy|shellcheck)\b"
)

# Trivially short / read-only commands that retry harmlessly. Matches the
# `case` list in the .sh.
_READ_ONLY_FIRST_TOKENS = {"ls", "pwd", "echo", "cat", "head", "tail", "grep"}

_STATE_DIRNAME = "dev-team-bash-retry"

# Same TTL-purge-on-write pattern as tdd_guard.py / mutation_adapters/lib.py
# (#732) — one state file is written per session with no expiry otherwise,
# so long-lived hosts accumulate a file per session forever.
_STATE_TTL_SECONDS = 14400  # 4 hours


def _cksum(text: str) -> str:
    """POSIX cksum-compatible hash for state-key/hash purposes.

    The .sh uses `cksum` (POSIX CRC + length). We use zlib.crc32 as a
    stable stdlib hash — byte-parity with the .sh is NOT required here
    because the state file is a private per-session artifact never
    surfaced to the user or committed to the repo. Determinism within
    the Python port is sufficient.
    """
    return str(zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF)


def _normalize(cmd: str) -> str:
    """Collapse runs of whitespace to a single space and trim ends."""
    return re.sub(r"\s+", " ", cmd).strip()


def _first_token(cmd: str) -> str:
    trimmed = _normalize(cmd)
    if not trimmed:
        return ""
    return trimmed.split(" ", 1)[0]


def _should_skip(cmd: str) -> bool:
    """True when this command class is out of scope (verify family or read-only)."""
    if _VERIFY_RE.search(cmd):
        return True
    return _first_token(cmd) in _READ_ONLY_FIRST_TOKENS


def _state_key(session_id: str, cwd: str) -> str:
    if session_id:
        return session_id
    return _cksum(cwd or os.getcwd())


def _purge_stale(state_dir: Path) -> None:
    if not state_dir.is_dir():
        return
    now = time.time()
    for path in state_dir.glob("*.json"):
        try:
            if now - path.stat().st_mtime > _STATE_TTL_SECONDS:
                path.unlink()
        except OSError:
            pass


def _state_file(state_key: str) -> Path:
    tmp = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))
    state_dir = tmp / _STATE_DIRNAME
    state_dir.mkdir(parents=True, exist_ok=True)
    _purge_stale(state_dir)
    return state_dir / f"{state_key}.json"


def _read_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"hash": "", "count": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"hash": "", "count": 0}
    return {
        "hash": str(data.get("hash", "") or ""),
        "count": int(data.get("count", 0) or 0),
    }


def _write_state(path: Path, state: dict[str, Any]) -> None:
    # Atomic (tempfile + rename) so a concurrent reader never sees a torn
    # file. The read-increment-write cycle is additionally serialized under
    # locked_state() in main() (#1501). Best-effort — advisory hook.
    atomic_write(path, json.dumps(state, separators=(",", ":")))


def main() -> int:
    payload = read_stdin_json()
    if payload is None:
        return 0

    tool_input = payload.get("tool_input") or {}
    command = str(tool_input.get("command") or "")
    if not command:
        return 0

    if _should_skip(command):
        return 0

    threshold = int(os.environ.get("DEV_TEAM_BASH_RETRY_THRESHOLD", "3") or "3")
    if threshold <= 0:
        # 0 disables the nudge entirely. Skip state accounting so a later
        # non-zero threshold doesn't fire on stale state.
        return 0

    session_id = str(payload.get("session_id") or "")
    cwd = str(payload.get("cwd") or "")
    state_key = _state_key(session_id, cwd)
    state_path = _state_file(state_key)

    normalized = _normalize(command)
    cur_hash = _cksum(normalized)

    # Serialize the read-increment-write so two concurrent invocations of the
    # same command (e.g. a shared-cwd state key across two sessions) each add
    # exactly one to the consecutive-run count instead of racing and losing an
    # increment (#1501). Fail-open: an unlockable environment runs unlocked.
    with locked_state(state_path):
        prev = _read_state(state_path)
        if cur_hash == prev["hash"]:
            count = prev["count"] + 1
        else:
            count = 1
        race_window_delay("DEV_TEAM_BASH_RETRY_TEST_DELAY_MS")
        _write_state(state_path, {"hash": cur_hash, "count": count})

    if count >= threshold:
        print(f"bash-retry-guard: This command has run {count} consecutive times.")
        print("  If it keeps failing, investigate the root cause rather than retrying.")
        print("  Set DEV_TEAM_BASH_RETRY_THRESHOLD=0 to disable this warning.")
        emit_boundary_event(cwd, "bash_retry_guard", "Bash", "warn", "bash-retry-threshold", session_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
