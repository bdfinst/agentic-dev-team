#!/usr/bin/env python3
"""iteration_journal_gate.py — hard per-iteration journal gate (#1168).

`/autoship`'s per-issue loop and `/ship`'s per-phase loop are model-authored
control flow inside a skill, not a tool call the PreToolUse/PostToolUse
harness intercepts — there is no hook-registration point distinct from any
other `Skill` invocation to gate specifically. This mirrors the same
constraint `workflow_state.py` (#1166) already documents for its
model-authored `record` append: enforcement lives in a library the skill's
prose invokes via CLI before it may advance, not in `settings.json`.

Two operations:
    record  — append a structured decision entry (what was attempted, the
              outcome, the next action) for the current round/iteration to
              `metrics/iteration-journal.jsonl`. Fail-open: an append error
              never raises into the calling skill.
    check   — hard-block: exit 1 (and emit a `boundary-events.jsonl` "block"
              record via `emit_boundary_event`) unless at least one entry
              exists for the given `--round-id`. Exit 0 (allowed) otherwise.

Complements, does not replace, `progress-guardian` (advisory, plan-step-keyed).
This gate is per-iteration, hard-blocking, and scoped to `/autoship`/`/ship`.

Stdlib only. Python 3.8+. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_LIB_DIR))

from boundary_events import emit_boundary_event

_LOG_NAME = "iteration-journal.jsonl"


def _isoformat_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_plugin_version() -> str:
    # hooks/lib/iteration_journal_gate.py -> hooks/lib -> hooks -> plugin root
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


def record_iteration_entry(
    cwd,
    round_id: str,
    attempted: str,
    outcome: str,
    next_action: str,
    session_id: str | None = None,
) -> None:
    """Append one compact JSON line recording this iteration's decision.

    Fail-open: any error (bad `cwd`, unwritable `metrics/`, disk full, etc.)
    is swallowed silently — an append failure must never crash the
    autonomous loop calling this.

    Args:
        cwd: Directory whose `metrics/` subdirectory receives the entry.
        round_id: Identifier for the current round/iteration (e.g.
            `/autoship`'s round_id, `/ship`'s issue identifier).
        attempted: Short structured string — what was attempted this
            iteration.
        outcome: Short structured string — what happened.
        next_action: Short structured string — what happens next.
        session_id: Optional opaque session ID, enabling joins with
            `boundary-events.jsonl` / `cost-metering.jsonl`.
    """
    try:
        log = _log_path(cwd)
        log.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "ts": _isoformat_utc(),
            "round_id": round_id,
            "attempted": attempted,
            "outcome": outcome,
            "next_action": next_action,
            "plugin_version": _load_plugin_version(),
        }
        if session_id:
            payload["session_id"] = session_id

        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except Exception:  # noqa: BLE001 — fail-open by design, see module docstring
        pass


def _read_entries(log: Path) -> list:
    if not log.is_file():
        return []
    entries = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return entries


def check_iteration_journal(
    round_id: str, cwd=None, log_path: str | None = None
) -> tuple[bool, str]:
    """Whether >=1 journal entry exists for `round_id`.

    Returns:
        `(True, "ok")` when a matching entry exists (advancement allowed).
        `(False, "iteration-journal-missing")` otherwise (advancement
        blocked).
    """
    log = Path(log_path) if log_path else _log_path(cwd)
    for entry in _read_entries(log):
        if entry.get("round_id") == round_id:
            return True, "ok"
    return False, "iteration-journal-missing"


def cmd_record(args) -> int:
    record_iteration_entry(
        args.cwd,
        args.round_id,
        args.attempted,
        args.outcome,
        args.next_action,
        args.session,
    )
    return 0


def cmd_check(args) -> int:
    allowed, reason = check_iteration_journal(args.round_id, args.cwd, args.log)
    print(json.dumps({"allowed": allowed, "reason": reason}))
    if allowed:
        return 0

    try:
        emit_boundary_event(
            args.cwd,
            hook="iteration_journal_gate",
            tool="Skill",
            decision="block",
            matched_rule="iteration-journal-missing",
            session_id=args.session,
        )
    except Exception:  # noqa: BLE001 — fail-open by design
        pass
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("record", help="Append one iteration decision entry.")
    p.add_argument("--cwd", default=None)
    p.add_argument("--round-id", dest="round_id", required=True)
    p.add_argument("--attempted", required=True)
    p.add_argument("--outcome", required=True)
    p.add_argument("--next-action", dest="next_action", required=True)
    p.add_argument("--session", default=None)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser(
        "check",
        help="Hard-block unless a journal entry exists for --round-id.",
    )
    p.add_argument("--cwd", default=None)
    p.add_argument("--log", default=None)
    p.add_argument("--round-id", dest="round_id", required=True)
    p.add_argument("--session", default=None)
    p.set_defaults(func=cmd_check)

    parsed = ap.parse_args(argv)
    return parsed.func(parsed)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
