#!/usr/bin/env python3
"""Python port of hooks/cost-meter.sh (#597 / #572 Phase 3).

Stop / SubagentStop hook (issue #102). PostToolUse hooks carry no token
usage, so this fires when a turn finishes, reads `transcript_path` from the
hook payload, and records a per-session cost summary (tokens + dollars, by
agent) to `metrics/cost-metering.jsonl` via
`hooks/lib/cost_meter.py record`.

Token→cost conversion uses `knowledge/model-pricing.json`.

Contract (docs/python-hook-contract.md):
    Input : Stop / SubagentStop JSON on stdin
    Output: writes metrics/cost-metering.jsonl; no stdout. Exit 0.
    Posture: record-only and fail-open. Any error → exit 0 silently.
    Opt-out: DEV_TEAM_COST_METER=off disables.

Thin dispatcher: the heavy lifting lives in the already-Python
`hooks/lib/cost_meter.py` module — this port replaces only the .sh
wrapper that reads the hook payload, resolves the log path, and shells
out to the library. Reuses the library directly via subprocess to keep
byte-parity with the .sh's stdout/stderr/exit behavior (record's own
stdout is suppressed in both cases).

Stdlib-only (json/os/pathlib/shutil/subprocess/sys). Python 3.8+.
See ADR 0014.

Refs: #572 (bash → Python migration epic).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_COST_METER_LIB = _HOOK_DIR / "lib" / "cost_meter.py"
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import telemetry_consent


def _read_stdin() -> str:
    try:
        return sys.stdin.read()
    except (OSError, ValueError):
        return ""


def _load_input(raw: str) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def main() -> int:
    # Opt-out short-circuit — matches the .sh's env-first check.
    if os.environ.get("DEV_TEAM_COST_METER") == "off":
        return 0
    if not telemetry_consent.is_enabled():
        return 0

    # Both jq and python3 must be present. The .sh checks both; the .py
    # only needs python3 (self-invocation), but we still check for the
    # library file so a broken checkout doesn't error out loudly.
    if shutil.which("python3") is None:
        return 0
    if not _COST_METER_LIB.is_file():
        return 0

    raw = _read_stdin()
    payload = _load_input(raw)
    if not payload:
        return 0

    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return 0
    if not Path(transcript).is_file():
        return 0

    cwd_hint = payload.get("cwd")
    if isinstance(cwd_hint, str) and cwd_hint and Path(cwd_hint).is_dir():
        cwd = cwd_hint
    else:
        cwd = os.getcwd()

    log_path = Path(cwd) / "metrics" / "cost-metering.jsonl"

    # Fire-and-forget: the .sh discards stdout/stderr and always exits 0.
    try:
        subprocess.run(
            [
                sys.executable,
                str(_COST_METER_LIB),
                "record",
                "--transcript",
                transcript,
                "--log",
                str(log_path),
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        pass

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
