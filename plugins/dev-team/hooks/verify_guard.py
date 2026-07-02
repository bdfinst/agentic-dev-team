#!/usr/bin/env python3
"""Python port of hooks/verify-guard.sh (#608 / #572 Phase 3).

PreToolUse Bash hook — detects repeated identical verify invocations
within a session and emits a convergence warning after THRESHOLD
consecutive identical runs. Nudges the agent to change approach rather
than re-run the same failing command.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin (hook_event_name, session_id,
            tool_input.command, cwd)
    Output: Warning on stdout; always exit 0 (advisory, never blocks)
    Env   : DEV_TEAM_VERIFY_THRESHOLD (default 3), TMPDIR

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import binascii
import json
import os
import re
import sys
import tempfile
from pathlib import Path


# Verify-class command detector — mirrors `session_extract.py::_VERIFY_RE`.
_VERIFY_RE = re.compile(
    r"\b("
    r"npm (run )?(test|lint|build)"
    r"|pytest|bats|eslint|tsc|go test|cargo (test|build)|mvn"
    r"|gradle|make( |$)|vitest|jest|ruff|mypy|shellcheck"
    r")\b"
)


def _tmpdir() -> Path:
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir() or "/tmp")


def _cksum(text: str) -> str:
    """Reproduce the `cksum` command's decimal CRC output.

    cksum(1) uses CRC-32/POSIX with a length-included final block. Python's
    binascii.crc32 does NOT match cksum's algorithm — cksum uses a different
    polynomial and treats input length as a byte suffix.

    Since the .sh only cares that hashes compare stably within a session
    (same input → same hash), we can use any deterministic hash. For byte
    parity across the .sh and .py implementations the parity harness pins
    both sides to the same input, so what matters is that BOTH sides use
    the SAME hash — that means we must actually call `cksum` here.
    """
    import subprocess

    # The .sh pipes `echo "$X" | cksum` — `echo` appends a LF that cksum
    # sees. Reproduce so both sides hash the same bytes.
    r = subprocess.run(
        ["cksum"],
        input=(text + "\n").encode(),
        capture_output=True,
        check=False,
    )
    if r.returncode != 0:
        return "0"
    return r.stdout.decode().split()[0]


def _read_payload() -> dict:
    try:
        raw = sys.stdin.buffer.read()
    except (OSError, ValueError):
        return {}
    try:
        return json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {}


def main() -> int:
    # The .sh short-circuits when jq is missing; here we rely on stdlib json
    # which is always present.
    payload = _read_payload()
    cmd = str(payload.get("tool_input", {}).get("command") or "")
    if not cmd:
        return 0

    # Only fire on verify-class commands.
    if not _VERIFY_RE.search(cmd):
        return 0

    session_id = str(payload.get("session_id") or "")
    cwd = str(payload.get("cwd") or "")
    # Prefer session_id, fall back to cksum of cwd (or $PWD when both empty).
    if session_id:
        state_key = session_id
    else:
        state_key = _cksum(cwd or os.getcwd())

    state_dir = _tmpdir() / "dev-team-verify-guard"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 0
    state_file = state_dir / f"{state_key}.json"

    # Normalize the command (collapse whitespace) for comparison.
    norm_cmd = " ".join(cmd.split())
    norm_hash = _cksum(norm_cmd)

    try:
        threshold = int(os.environ.get("DEV_TEAM_VERIFY_THRESHOLD", "3"))
    except ValueError:
        threshold = 3

    prev_hash = ""
    count = 0
    if state_file.is_file():
        try:
            prev = json.loads(state_file.read_text())
            prev_hash = str(prev.get("hash") or "")
            count = int(prev.get("count") or 0)
        except (OSError, json.JSONDecodeError, ValueError):
            prev_hash = ""
            count = 0

    if norm_hash == prev_hash:
        count += 1
    else:
        count = 1

    # Write updated state. Bash's `jq -nc ... >file` adds a trailing LF;
    # match byte-for-byte.
    try:
        state_file.write_text(
            json.dumps(
                {"hash": norm_hash, "count": count},
                separators=(",", ":"),
            )
            + "\n"
        )
    except OSError:
        pass

    # Match the .sh's `[ "$count" -ge "$THRESHOLD" ]` — threshold=0 always
    # fires the warning even on the first run. The .sh's "set to 0 to
    # suppress" line is technically misleading (it suppresses NOTHING when
    # count is >= 0), but byte-parity is the contract.
    if count >= threshold:
        print(
            f"verify-guard: This verify command has run {count} consecutive "
            "times without a code change."
        )
        print(
            "  If the tests are still failing, change the code rather than "
            "re-running the same command."
        )
        print("  To suppress this warning, set DEV_TEAM_VERIFY_THRESHOLD=0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
