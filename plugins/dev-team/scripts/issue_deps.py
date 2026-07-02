#!/usr/bin/env python3
"""Python port of scripts/issue-deps.sh (#614 / #572 Phase 3).

Per-slice sibling dependency sets for issue linking, derived from the plan's
DAG (via plan_waves.py), NOT from plan file order. Read-only: never edits the
plan or plan-waves output.

Emits JSON mapping each slice id to its DIRECT predecessor slice ids:

    { "A": [], "B": ["A"], "C": ["A"], "D": ["B","C"] }

/issues-from-plan maps those slice ids to the child issue numbers it creates
and renders "depends on #N" links between siblings.

Usage: issue_deps.py <plan.md>

Delegates DAG analysis to plan_waves.py — same reason as build_wave.py: until
plan_waves.py converts, calling into it preserves the single source of truth
for cycle / missing / unknown-dep diagnostics.

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _here() -> Path:
    return Path(__file__).resolve().parent


def _run_plan_waves(plan_file: str):
    plan_waves = _here() / "plan_waves.py"
    return subprocess.run(
        [sys.executable, str(plan_waves), plan_file],
        capture_output=True,
        text=True,
        check=False,
    )


def main(argv: list) -> int:
    if len(argv) < 2 or not argv[1] or not os.path.isfile(argv[1]):
        print("usage: issue-deps.sh <plan.md>", file=sys.stderr)
        return 2

    result = _run_plan_waves(argv[1])
    if result.returncode != 0:
        # Propagate plan-waves' error + exit code verbatim.
        sys.stderr.write(result.stderr)
        return result.returncode

    try:
        waves_json = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"issue-deps: plan_waves.py emitted invalid JSON: {exc}", file=sys.stderr)
        return 1

    # `.slices | map_values(.depends_on)` in jq → { <sid>: [<dep>, …] }.
    slices = waves_json.get("slices") or {}
    out = {sid: (spec.get("depends_on") or []) for sid, spec in slices.items()}

    # jq's default pretty-print: 2-space indent, LF terminator.
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
