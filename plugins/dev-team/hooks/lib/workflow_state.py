#!/usr/bin/env python3
"""workflow_state.py — workflow state-machine event stream (#1166).

Persists only state-*transition* events for orchestrated flows (`/ship`,
`/autoship`, `/build`) to `metrics/workflow-states.jsonl` — never a
current-state snapshot. Current state and per-state dwell time are always
*derived* by replaying the stream for a given `session_id`, mirroring the
event-sourcing discipline described in the competitive analysis this issue
is drawn from (see knowledge/telemetry-schema.md). No SQLite, no MCP
projection server — the append-only JSONL substrate is unchanged.

Canonical lifecycle (informational only — `new_state` is not validated
against it, since ad-hoc workflows may define their own):
    SPEC -> PLAN -> BUILD -> REVIEW -> COMMIT -> PR

Fail-open on emit: every exception is swallowed. A full disk, read-only
`metrics/`, or malformed state must never raise into the caller.

Stdlib only. Python 3.8+. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_LOG_NAME = "workflow-states.jsonl"

CANONICAL_LIFECYCLE = ["SPEC", "PLAN", "BUILD", "REVIEW", "COMMIT", "PR"]


def _isoformat_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_plugin_version() -> str:
    # hooks/lib/workflow_state.py -> hooks/lib -> hooks -> plugin root
    manifest = Path(__file__).resolve().parents[2] / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        version = data.get("version")
        if isinstance(version, str) and version:
            return version
    except (OSError, ValueError):
        pass
    return "unknown"


def _log_path(cwd) -> Path:
    base = Path(cwd) if cwd else Path.cwd()
    return base / "metrics" / _LOG_NAME


def emit_state_transition(
    cwd,
    workflow: str,
    prior_state: str | None,
    new_state: str,
    session_id: str | None = None,
) -> None:
    """Append one compact JSON line recording a state transition.

    Fail-open: any error (bad `cwd`, unwritable `metrics/`, disk full,
    etc.) is swallowed silently.

    Args:
        cwd: Directory whose `metrics/` subdirectory receives the event.
        workflow: Orchestrated flow name, e.g. "ship", "autoship", "build".
        prior_state: State the workflow was in before this transition, or
            `None`/empty string for the initial transition into the first
            state of a run.
        new_state: State the workflow is entering.
        session_id: Optional opaque session ID, enabling per-session joins
            with `boundary-events.jsonl` and `cost-metering.jsonl`.
    """
    try:
        log = _log_path(cwd)
        log.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "ts": _isoformat_utc(),
            "workflow": workflow,
            "prior_state": prior_state or None,
            "new_state": new_state,
            "plugin_version": _load_plugin_version(),
        }
        if session_id:
            payload["session_id"] = session_id

        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except Exception:  # noqa: BLE001, S110 — fail-open by design, see module docstring
        pass


def _read_transitions(log: Path, session_id: str | None = None) -> list:
    if not log.is_file():
        return []
    entries = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if session_id and event.get("session_id") != session_id:
            continue
        entries.append(event)
    return entries


def _parse_ts(ts: str):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def derive_current_state(entries: list) -> str | None:
    """The most recent `new_state` across the given (already session-filtered,
    chronological) transitions, or `None` if there are no entries."""
    if not entries:
        return None
    return entries[-1].get("new_state")


def compute_dwell_times(entries: list, now=None) -> dict:
    """Per-state dwell time in seconds, derived by replay.

    Each state's dwell time is the gap between the transition that entered
    it and the transition that left it. The current (last) state's dwell
    time runs from its entry transition to `now` (defaults to wall-clock
    UTC), so an in-flight run reports a live, growing duration rather than
    zero.
    """
    dwell: dict = {}
    if not entries:
        return dwell

    if now is None:
        now = datetime.now(timezone.utc)

    for idx, event in enumerate(entries):
        state = event.get("new_state")
        if not state:
            continue
        start = _parse_ts(event["ts"])
        if idx + 1 < len(entries):
            end = _parse_ts(entries[idx + 1]["ts"])
        else:
            end = now
        dwell[state] = dwell.get(state, 0.0) + max(0.0, (end - start).total_seconds())

    return dwell


def cmd_record(args) -> int:
    emit_state_transition(
        args.cwd,
        args.workflow,
        args.prior_state,
        args.new_state,
        args.session,
    )
    return 0


def cmd_report(args) -> int:
    log = Path(args.log) if args.log else _log_path(args.cwd)
    entries = _read_transitions(log, args.session)
    result = {
        "session_id": args.session,
        "current_state": derive_current_state(entries),
        "dwell_seconds": compute_dwell_times(entries),
        "transition_count": len(entries),
    }
    print(json.dumps(result, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("record", help="Append one state-transition event.")
    p.add_argument("--cwd", default=None)
    p.add_argument("--workflow", required=True)
    p.add_argument("--prior-state", dest="prior_state", default=None)
    p.add_argument("--new-state", dest="new_state", required=True)
    p.add_argument("--session", default=None)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser(
        "report", help="Derive current state + per-state dwell time for a session."
    )
    p.add_argument("--cwd", default=None)
    p.add_argument("--log", default=None)
    p.add_argument("--session", default=None)
    p.set_defaults(func=cmd_report)

    parsed = ap.parse_args(argv)
    return parsed.func(parsed)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
