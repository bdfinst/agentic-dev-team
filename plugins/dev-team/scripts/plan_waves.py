#!/usr/bin/env python3
"""plan_waves.py — compute parallel build waves from a plan's slice DAG.

Python port of `scripts/plan-waves.sh` (#589 / #572 Phase 2 Cluster E1).

Parses each slice's `Depends-on`, topologically layers the DAG into waves
(wave 1 = slices with no prerequisites), detects same-wave file collisions,
and emits a stable JSON contract (schema `plan-waves/v1`) on stdout:

    { "schema", "waves": [[id,...],...],
      "slices": {id:{depends_on,files,wave}},
      "collisions": [{wave, slices:[a,b], file}] }

Rejects (exit 2, message on stderr):
  - a dependency cycle
  - a slice missing its Depends-on declaration
  - an unknown dependency reference

Uses `scripts/lib/plan_parse.py` for the parser stage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import plan_parse  # noqa: E402


_TOKEN_SPLIT_RE = re.compile(r"[,\s]+")


def _die(message: str) -> None:
    sys.stderr.write("plan-waves: " + message + "\n")
    sys.exit(2)


def compute_waves(plan_path: Path) -> dict:
    """Return the plan-waves/v1 JSON payload for `plan_path`."""
    rows = plan_parse.parse_slices(plan_path.read_text().splitlines())

    slices: Dict[str, dict] = {}
    order: List[str] = []
    for sid, deps_raw, files_raw in rows:
        files = [f for f in _TOKEN_SPLIT_RE.split(files_raw) if f]
        slices[sid] = {"deps_raw": deps_raw, "files": files}
        order.append(sid)

    if not slices:
        _die("no slices found (expected '### Slice <id>: ...' headings)")

    for sid in order:
        deps_raw = slices[sid]["deps_raw"]
        if deps_raw == "__MISSING__":
            _die(
                f"slice {sid!r} is missing its Depends-on declaration — "
                "add 'Depends-on: none' if it has no prerequisites."
            )
        raw = deps_raw.strip()
        if raw.lower() == "none" or raw == "":
            slices[sid]["deps"] = []
        else:
            slices[sid]["deps"] = [d for d in _TOKEN_SPLIT_RE.split(raw) if d]

    for sid in order:
        for dep in slices[sid]["deps"]:
            if dep not in slices:
                _die(f"slice {sid!r} depends on unknown slice {dep!r}.")

    remaining = {sid: set(slices[sid]["deps"]) for sid in order}
    waves: List[List[str]] = []
    placed: set = set()
    while remaining:
        ready = sorted(s for s, d in remaining.items() if d <= placed)
        if not ready:
            _die("dependency cycle among slices: " + ", ".join(sorted(remaining)) + ".")
        waves.append(ready)
        for s in ready:
            placed.add(s)
            del remaining[s]

    wave_of = {s: i for i, wave in enumerate(waves, 1) for s in wave}

    collisions: List[dict] = []
    for i, wave in enumerate(waves, 1):
        for a in range(len(wave)):
            for b in range(a + 1, len(wave)):
                shared = sorted(
                    set(slices[wave[a]]["files"]) & set(slices[wave[b]]["files"])
                )
                for f in shared:
                    collisions.append(
                        {"wave": i, "slices": [wave[a], wave[b]], "file": f}
                    )

    return {
        "schema": "plan-waves/v1",
        "waves": waves,
        "slices": {
            sid: {
                "depends_on": slices[sid]["deps"],
                "files": slices[sid]["files"],
                "wave": wave_of[sid],
            }
            for sid in order
        },
        "collisions": collisions,
    }


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan_waves.py",
        description="Compute parallel build waves from a plan's slice DAG.",
    )
    parser.add_argument("plan", nargs="?", help="Path to the plan markdown file")
    args = parser.parse_args(argv)
    if not args.plan:
        sys.stderr.write("usage: plan-waves.sh <plan.md>\n")
        return 2
    plan_path = Path(args.plan)
    if not plan_path.is_file():
        sys.stderr.write("usage: plan-waves.sh <plan.md>\n")
        return 2
    payload = compute_waves(plan_path)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
