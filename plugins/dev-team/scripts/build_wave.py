#!/usr/bin/env python3
"""Python port of scripts/build-wave.sh (#611 / #572 Phase 3).

Emit the build's wave schedule, derived from plan_waves.py. Each wave lists
its members and a deterministic reconcile order (members sorted) so a wave
merges reproducibly regardless of completion order:

    { "schema": "build-wave/v1",
      "waves": [ { "wave": 1, "members": [...], "reconcile_order": [...] } ],
      "collisions": [...] }

Exits non-zero if the plan is invalid (cycle / missing / unknown — surfaced by
plan_waves.py) OR if any wave has a declared same-file collision: a wave with
a collision must not be built concurrently, so the build refuses it here.

Usage: build_wave.py <plan.md>

Delegates DAG analysis to plan_waves.py (the authoritative implementation
until its own port lands per #572). Once plan_waves.py is ported to Python,
switch the subprocess call for a direct import.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _here() -> Path:
    return Path(__file__).resolve().parent


def _run_plan_waves(plan_file: str) -> tuple[str, int, str]:
    """Return (stdout, exit_code, stderr) from `plan_waves.py <plan.md>`."""
    plan_waves = _here() / "plan_waves.py"
    completed = subprocess.run(
        [sys.executable, str(plan_waves), plan_file],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout, completed.returncode, completed.stderr


def _reshape(waves_json: dict) -> dict:
    """Reshape plan-waves output into the build-wave/v1 schedule schema."""
    reshaped_waves = []
    for i, members in enumerate(waves_json.get("waves", []), start=1):
        reshaped_waves.append(
            {
                "wave": i,
                "members": members,
                "reconcile_order": sorted(members),
            }
        )
    return {
        "schema": "build-wave/v1",
        "waves": reshaped_waves,
        "collisions": waves_json.get("collisions", []),
    }


def main(argv: list) -> int:
    if len(argv) < 2 or not argv[1] or not os.path.isfile(argv[1]):
        print("usage: build_wave.py <plan.md>", file=sys.stderr)
        return 2

    plan_file = argv[1]
    stdout, code, stderr = _run_plan_waves(plan_file)
    if code != 0:
        # Propagate plan_waves.py's error output verbatim + exit code.
        sys.stderr.write(stderr)
        return code

    try:
        waves_json = json.loads(stdout)
    except json.JSONDecodeError as exc:
        print(f"build-wave: plan_waves.py emitted invalid JSON: {exc}", file=sys.stderr)
        return 1

    reshaped = _reshape(waves_json)
    # jq default pretty-print uses 2-space indent, sort keys, LF terminator.
    print(json.dumps(reshaped, indent=2))

    # Refuse a schedule that contains a same-wave file collision.
    collisions = waves_json.get("collisions") or []
    if collisions:
        print(
            "build-wave: same-wave file collision(s) — cannot build this "
            "wave concurrently:",
            file=sys.stderr,
        )
        for c in collisions:
            slices = " + ".join(c.get("slices", []))
            print(
                f"  wave {c.get('wave')}: {slices} both touch {c.get('file')}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
