#!/usr/bin/env python3
"""subagent_liveness.py — list subagents that stopped making progress.

An agent is hung when its transcript (`<dir>/agent-<id>.jsonl`) has not been
written for more than the threshold and no `SubagentStop` row names it. Stop
rows come from `.claude/metrics/subagent-stops.jsonl`, which
`hooks/subagent_completion_guard.py` appends to (with `agent_id`) on every stop.

    subagent_liveness.py --dir <session>/subagents [--stops <jsonl>] [--threshold-seconds N]

Prints `{"schema": "subagent-liveness/v1", "threshold_seconds", "hung": [...]}`.
Exit 1 when a hung agent exists so a poller can act; 0 otherwise.
Default threshold: 600 s, or env `DEV_TEAM_SUBAGENT_STUCK_SECONDS`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

DEFAULT_THRESHOLD_SECONDS = 600
_THRESHOLD_ENV = "DEV_TEAM_SUBAGENT_STUCK_SECONDS"


def default_threshold() -> int:
    try:
        return int(os.environ[_THRESHOLD_ENV])
    except (KeyError, ValueError):
        return DEFAULT_THRESHOLD_SECONDS


def _stopped_ids(stops: Path | None) -> set[str]:
    ids: set[str] = set()
    if stops is None or not stops.is_file():
        return ids
    for line in stops.read_text(errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and isinstance(row.get("agent_id"), str):
            ids.add(row["agent_id"])
    return ids


def find_hung(
    subagent_dir: Path, stops: Path | None, threshold: float, now: float | None = None
) -> list[dict]:
    if not subagent_dir.is_dir():
        return []
    now = time.time() if now is None else now
    stopped = _stopped_ids(stops)
    hung = []
    for path in sorted(subagent_dir.glob("agent-*.jsonl")):
        agent_id = path.stem.removeprefix("agent-")
        if agent_id in stopped:
            continue
        idle = now - path.stat().st_mtime
        if idle > threshold:
            hung.append({"agent_id": agent_id, "idle_seconds": round(idle), "transcript": str(path)})
    return hung


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="subagent_liveness.py", description=__doc__.splitlines()[0])
    parser.add_argument("--dir", required=True, help="the session's subagents/ directory")
    parser.add_argument("--stops", help="subagent-stops.jsonl path")
    parser.add_argument("--threshold-seconds", type=int, default=None)
    args = parser.parse_args(argv)
    threshold = args.threshold_seconds if args.threshold_seconds is not None else default_threshold()
    hung = find_hung(Path(args.dir), Path(args.stops) if args.stops else None, threshold)
    print(
        json.dumps(
            {"schema": "subagent-liveness/v1", "threshold_seconds": threshold, "hung": hung},
            indent=2,
        )
    )
    return 1 if hung else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
