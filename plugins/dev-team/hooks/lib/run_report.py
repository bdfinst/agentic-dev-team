#!/usr/bin/env python3
"""run_report.py — per-session run report (#1167).

Composes one `session_id`'s view across three existing streams:
`metrics/boundary-events.jsonl` (denials/bypasses), `metrics/cost-metering.jsonl`
(tokens/$), and `metrics/workflow-states.jsonl` (#1166, state dwell times).
Pure composition of already-deterministic data — no model tokens spent
parsing transcripts.

Join limitation (cost): `cost-metering.jsonl` entries are keyed by transcript
filename (see `hooks/lib/cost_meter.py::cmd_record()`), not `session_id` — the
Stop hook that writes it never learns the session ID. There is no reliable
join key today, so `cost` in the report is explicitly marked `joinable:
false` rather than guessing an attribution the data doesn't support.

Stdlib only. Python 3.8+. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import workflow_state  # noqa: E402


def _metrics_dir(cwd) -> Path:
    return (Path(cwd) if cwd else Path.cwd()) / "metrics"


def _read_jsonl(path: Path) -> list:
    if not path.is_file():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return entries


def _most_recent_session_id(cwd) -> Optional[str]:
    """Most recent `session_id` across boundary-events + workflow-states,
    by event order within each stream (both are append-only chronological
    logs, so the last matching entry is the most recent)."""
    metrics = _metrics_dir(cwd)
    candidates = _read_jsonl(metrics / "boundary-events.jsonl") + _read_jsonl(
        metrics / "workflow-states.jsonl"
    )
    for event in reversed(candidates):
        session_id = event.get("session_id")
        if session_id:
            return session_id
    return None


def _boundary_summary(cwd, session_id: str) -> dict:
    metrics = _metrics_dir(cwd)
    events = [
        e
        for e in _read_jsonl(metrics / "boundary-events.jsonl")
        if e.get("session_id") == session_id
    ]
    rejection_count = sum(1 for e in events if e.get("decision") == "block")
    bypass_count = sum(1 for e in events if e.get("decision") == "bypass")
    denials_by_cause: dict = {}
    for e in events:
        if e.get("decision") in ("block", "warn"):
            cause = e.get("matched_rule", "unknown")
            denials_by_cause[cause] = denials_by_cause.get(cause, 0) + 1
    return {
        "rejection_count": rejection_count,
        "bypass_count": bypass_count,
        "denials_by_cause": denials_by_cause,
    }


def _cost_summary(cwd) -> dict:
    """Best-effort cost section — see module docstring for why this can't be
    a real per-session join today."""
    metrics = _metrics_dir(cwd)
    entries = _read_jsonl(metrics / "cost-metering.jsonl")
    if not entries:
        return {"joinable": False, "reason": "no cost-metering.jsonl entries recorded"}
    latest = entries[-1]
    return {
        "joinable": False,
        "reason": (
            "cost-metering.jsonl is keyed by transcript filename, not "
            "session_id — no reliable join key exists yet"
        ),
        "most_recent_entry": {
            "transcript": latest.get("transcript"),
            "total": latest.get("total"),
        },
    }


def build_report(cwd, session_id: Optional[str] = None) -> dict:
    if not session_id:
        session_id = _most_recent_session_id(cwd)

    metrics = _metrics_dir(cwd)
    if session_id:
        transitions = workflow_state._read_transitions(
            metrics / "workflow-states.jsonl", session_id
        )
        boundary = _boundary_summary(cwd, session_id)
    else:
        transitions = []
        boundary = {"rejection_count": 0, "bypass_count": 0, "denials_by_cause": {}}

    return {
        "session_id": session_id,
        "current_state": workflow_state.derive_current_state(transitions),
        "dwell_seconds": workflow_state.compute_dwell_times(transitions),
        "rejection_count": boundary["rejection_count"],
        "denials_by_cause": boundary["denials_by_cause"],
        "bypass_count": boundary["bypass_count"],
        "cost": _cost_summary(cwd),
    }


def cmd_report(args) -> int:
    report = build_report(args.cwd, args.session)
    print(json.dumps(report, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "report", help="Join boundary/cost/workflow-state streams for one session."
    )
    p.add_argument("--cwd", default=None)
    p.add_argument("--session", default=None)
    p.set_defaults(func=cmd_report)

    parsed = ap.parse_args(argv)
    return parsed.func(parsed)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
