#!/usr/bin/env python3
"""Per-lens review finding categories at /build checkpoints (#2211).

``append`` adds one JSONL row per finding to
``.claude/metrics/review-findings.jsonl`` and is fail-open (never raises, never
blocks a phase). ``report`` ranks ``(lens, category)`` by frequency and
first-pass-fix rate, so authoring checklists promote only the categories that
actually fire.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG = Path(".claude/metrics/review-findings.jsonl")


def append(path: Path, lens: str, category: str, severity: str,
           iteration: int, fixed: bool) -> bool:
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "lens": lens, "category": category, "severity": severity,
        "iteration": iteration, "fixed": fixed,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        return True
    except OSError:
        return False


def rank(rows) -> list[dict]:
    """Group by (lens, category); first-pass-fix = fixed at iteration 1."""
    groups: dict = defaultdict(lambda: {"count": 0, "first_pass_fixed": 0})
    for r in rows:
        g = groups[(r["lens"], r["category"])]
        g["count"] += 1
        if r.get("fixed") and r.get("iteration") == 1:
            g["first_pass_fixed"] += 1
    out = [
        {"lens": lens, "category": cat, "count": g["count"],
         "first_pass_fix_rate": round(g["first_pass_fixed"] / g["count"], 2)}
        for (lens, cat), g in groups.items()
    ]
    return sorted(out, key=lambda d: (-d["count"], d["lens"], d["category"]))


def load(path: Path) -> list[dict]:
    rows = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and {"lens", "category"} <= row.keys():
                    rows.append(row)
    except OSError:
        pass
    return rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--log", type=Path, default=DEFAULT_LOG)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append")
    a.add_argument("--lens", required=True)
    a.add_argument("--category", required=True)
    a.add_argument("--severity", default="unknown")
    a.add_argument("--iteration", type=int, default=1)
    a.add_argument("--fixed", action="store_true")
    sub.add_parser("report")
    args = p.parse_args(argv)
    if args.cmd == "append":
        append(args.log, args.lens, args.category, args.severity,
               args.iteration, args.fixed)
        return 0  # fail-open
    print(json.dumps(rank(load(args.log)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
