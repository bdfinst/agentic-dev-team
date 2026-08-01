#!/usr/bin/env python3
"""phase_marker — PostToolUse:Skill hook (issue #1520).

A phase boundary in the three-phase workflow is where the orchestrator
compacts context before the next phase — i.e. where `/handoff` (continue
mode) runs. This hook fires on every Skill invocation, filters to `handoff`,
and records a context-pollution marker via `hooks/lib/cost_meter.py
phase-mark`: the main-loop resident context occupancy at the boundary and the
cumulative output spend so far. `cost-report`'s `phase-report` later turns the
sequence of markers into per-phase resident-vs-spent ratios — the distinction
between context that lingered (pollution) and one-time cost that the session
totals cannot make.

Why a hook and not a prose instruction: the emission has to be reliable, not
dependent on the orchestrator remembering to call a script (hooks enforce, prose
gets ignored). PostToolUse hooks carry no token usage, but they DO carry
`transcript_path`, and the cost-meter library derives resident/spent by parsing
the transcript — the same mechanism the Stop-hook cost meter uses.

Contract (docs/python-hook-contract.md):
    Input : PostToolUse:Skill JSON on stdin
    Output: appends .claude/metrics/phase-markers.jsonl; no stdout. Exit 0.
    Posture: record-only and fail-open. Any error → exit 0 silently.
    Opt-out: DEV_TEAM_COST_METER=off disables (shares the cost meter's switch).

Stdlib-only. See ADR 0014.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_COST_METER_LIB = _HOOK_DIR / "lib" / "cost_meter.py"
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
import telemetry_consent

# Skill label sanity — same shape the telemetry hook accepts for a skill name.
_LABEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _load_input() -> dict:
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _phase_label(tool_input: dict) -> str:
    """Best-effort phase label for the marker.

    `/handoff`'s args may name the phase being closed (e.g. `research`); when
    present and sane, use it, else fall back to the neutral `handoff` label.
    The per-phase report is still meaningful with neutral labels — the
    resident/spent delta between consecutive markers is the signal — a label
    only makes the row easier to read.
    """
    args = tool_input.get("args")
    if isinstance(args, str):
        first = args.strip().split()[0] if args.strip() else ""
        if _LABEL_RE.match(first):
            return first
    return "handoff"


def main() -> int:
    if os.environ.get("DEV_TEAM_COST_METER") == "off":
        return 0
    if not telemetry_consent.is_enabled():
        return 0
    if shutil.which("python3") is None or not _COST_METER_LIB.is_file():
        return 0

    payload = _load_input()
    if not payload:
        return 0

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    skill = tool_input.get("skill") or tool_input.get("name") or ""
    if not isinstance(skill, str) or skill != "handoff":
        return 0

    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript or not Path(transcript).is_file():
        return 0

    cwd_hint = payload.get("cwd")
    if isinstance(cwd_hint, str) and cwd_hint and Path(cwd_hint).is_dir():
        cwd = cwd_hint
    else:
        cwd = os.getcwd()

    log_path = artifact_paths.resolve_file("metrics", "phase-markers.jsonl", cwd)

    try:
        subprocess.run(
            [
                sys.executable,
                str(_COST_METER_LIB),
                "phase-mark",
                "--transcript",
                transcript,
                "--phase",
                _phase_label(tool_input),
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
