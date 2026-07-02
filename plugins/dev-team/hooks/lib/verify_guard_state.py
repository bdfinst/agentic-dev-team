"""Shared per-session state helpers for verify_guard.py and
verify_guard_edit_marker.py (#708).

verify_guard.py (PreToolUse `Bash`) needs to tell a genuinely stuck loop
(the same verify command run over and over with zero intervening code
changes) apart from ordinary TDD re-verification (RED, GREEN, REFACTOR
each legitimately re-run the same command, but each preceded by a real
edit). The two hooks communicate that signal through one JSON state file
per session, keyed identically by both hooks — so this module exists to
make sure "identically" is actually true, rather than two independently
maintained copies of the same hashing/keying logic drifting apart.

State shape (JSON object): ``{"hash": str, "count": int, "edited": bool}``.
``hash`` and ``count`` are verify_guard.py's consecutive-identical-command
counter; ``edited`` is set true by verify_guard_edit_marker.py whenever an
Edit/Write/NotebookEdit tool call is observed, and consumed (reset to
false) by verify_guard.py on its next run.

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

_STATE_DIRNAME = "dev-team-verify-guard"

# Same TTL-purge-on-write pattern as tdd_guard.py / mutation_adapters/lib.py
# (#732) — one state file is written per session with no expiry otherwise,
# so long-lived hosts accumulate a file per session forever.
_STATE_TTL_SECONDS = 14400  # 4 hours


def cksum(text: str) -> str:
    """Reproduce the `cksum` command's decimal CRC output.

    cksum(1) uses CRC-32/POSIX with a length-included final block; Python's
    binascii.crc32 does not match it. What matters here is that BOTH hooks
    hash the same way, so the state key/hash they compute for the same
    session agrees — hence the shared helper rather than two copies.
    """
    r = subprocess.run(
        ["cksum"],
        input=(text + "\n").encode(),
        capture_output=True,
        check=False,
    )
    if r.returncode != 0:
        return "0"
    return r.stdout.decode().split()[0]


def tmpdir() -> Path:
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir() or "/tmp")


def state_dir() -> Path:
    return tmpdir() / _STATE_DIRNAME


def state_key(session_id: str, cwd: str) -> str:
    """Prefer session_id, fall back to cksum of cwd (or $PWD when both empty)."""
    if session_id:
        return session_id
    return cksum(cwd or os.getcwd())


def state_file(key: str) -> Path:
    return state_dir() / f"{key}.json"


def read_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def purge_stale(directory: Path) -> None:
    """Delete `*.json` state files in `directory` untouched past the TTL.

    Both verify_guard.py and verify_guard_edit_marker.py write through
    `write_state`, so calling this there is the single choke point that
    keeps the shared state dir from accumulating one file per session
    forever (#732).
    """
    if not directory.is_dir():
        return
    now = time.time()
    for path in directory.glob("*.json"):
        try:
            if now - path.stat().st_mtime > _STATE_TTL_SECONDS:
                path.unlink()
        except OSError:
            pass


def write_state(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    purge_stale(path.parent)
    try:
        path.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    except OSError:
        pass
