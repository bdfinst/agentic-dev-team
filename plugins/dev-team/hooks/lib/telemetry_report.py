#!/usr/bin/env python3
"""Telemetry report (issues #106, #135).

Aggregates the opt-in, privacy-clean event log written by hooks/telemetry.sh
(metrics/telemetry.jsonl) into: command usage counts, skill usage counts
(including agent-/auto-invoked skills, counted distinctly from user-typed
commands — #135), and the pre-commit review gate's bypass rate
(bypassed / (fired + bypassed)). With telemetry disabled the log doesn't exist
and this reports that nothing was collected — satisfying "with it disabled,
nothing leaves the machine."

Usage: telemetry_report.py [--log metrics/telemetry.jsonl] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def aggregate(log: Path) -> dict:
    commands: Counter = Counter()
    skills: Counter = Counter()
    gate_by_name: dict[str, Counter] = {}
    total_events = 0
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        total_events += 1
        if e.get("event") == "command":
            commands[e.get("name", "?")] += 1
        elif e.get("event") == "skill":
            skills[e.get("name", "?")] += 1
        elif e.get("event") == "gate":
            name = e.get("name", "?")
            gate_by_name.setdefault(name, Counter())[e.get("outcome", "?")] += 1

    gate_summary = {}
    for name, oc in gate_by_name.items():
        fired = oc.get("fired", 0)
        bypassed = oc.get("bypassed", 0)
        denom = fired + bypassed
        gate_summary[name] = {
            "fired": fired,
            "bypassed": bypassed,
            "bypass_rate": round(bypassed / denom, 4) if denom else 0.0,
        }
    return {
        "total_events": total_events,
        "command_usage": dict(commands.most_common()),
        "skill_usage": dict(skills.most_common()),
        "gates": gate_summary,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", default="metrics/telemetry.jsonl")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    log = Path(args.log)
    if not log.is_file():
        print("Telemetry is off (or no events recorded): "
              f"{log} does not exist. Nothing has left the machine.")
        return 0

    summary = aggregate(log)
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print(f"# Telemetry report — {summary['total_events']} event(s)\n")
    print("## Command usage (user-typed slash commands)")
    if summary["command_usage"]:
        for name, n in summary["command_usage"].items():
            print(f"  /{name}: {n}")
    else:
        print("  (none)")
    print("\n## Skill usage (incl. agent-/auto-invoked)")
    if summary["skill_usage"]:
        for name, n in summary["skill_usage"].items():
            print(f"  {name}: {n}")
    else:
        print("  (none)")
    print("\n## Gate bypass rates")
    if summary["gates"]:
        for name, g in summary["gates"].items():
            print(f"  {name}: {g['bypassed']} bypassed / "
                  f"{g['fired'] + g['bypassed']} attempts "
                  f"({g['bypass_rate'] * 100:.1f}% bypassed)")
    else:
        print("  (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
