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
import fnmatch
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import plan_parse

_TOKEN_SPLIT_RE = re.compile(r"[,\s]+")


def _die(message: str) -> None:
    sys.stderr.write("plan-waves: " + message + "\n")
    sys.exit(2)


def _is_glob(pattern: str) -> bool:
    return any(ch in pattern for ch in "*?[")


def _file_covered(file_path: str, patterns: list[str]) -> bool:
    """True when `file_path` exactly matches a declared pattern, or a
    declared glob pattern (fnmatch, stdlib — #865 AC9) matches it."""
    for pattern in patterns:
        if pattern == file_path:
            return True
        if _is_glob(pattern) and fnmatch.fnmatch(file_path, pattern):
            return True
    return False


def _pattern_covers_any(pattern: str, files: list[str]) -> bool:
    """True when a declared `pattern` is satisfied by at least one inferred
    file — an exact-match hit, or (for a glob pattern) any fnmatch hit."""
    for file_path in files:
        if pattern == file_path:
            return True
        if _is_glob(pattern) and fnmatch.fnmatch(file_path, pattern):
            return True
    return False


def _scope_mismatch(sid: str, declared: list[str], inferred: list[str]) -> dict:
    """Return a `scope_mismatches` entry for `sid`, or `None` when the
    declared and inferred sets reconcile (#865 AC3). `under_declared` is the
    dangerous direction: a step plans to touch a file the slice never
    declared. `over_declared` is a declared path/pattern nothing inferred
    actually touches."""
    under_declared = sorted(f for f in inferred if not _file_covered(f, declared))
    over_declared = sorted(p for p in declared if not _pattern_covers_any(p, inferred))
    if not under_declared and not over_declared:
        return None
    return {
        "slice": sid,
        "declared": sorted(declared),
        "inferred": sorted(inferred),
        "under_declared": under_declared,
        "over_declared": over_declared,
    }


def compute_waves(plan_path: Path) -> dict:
    """Return the plan-waves/v1 JSON payload for `plan_path`."""
    plan_lines = plan_path.read_text().splitlines()
    rows = plan_parse.parse_slices(plan_lines)
    inferred_by_slice = plan_parse.step_files_union(plan_lines)

    slices: dict[str, dict] = {}
    order: list[str] = []
    for sid, deps_raw, files_raw in rows:
        files = [f for f in _TOKEN_SPLIT_RE.split(files_raw) if f]
        slices[sid] = {
            "deps_raw": deps_raw,
            "files": files,
            "inferred_files": inferred_by_slice.get(sid, []),
        }
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
    waves: list[list[str]] = []
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

    # Conservative same-wave collision detection (#865): compare the union of
    # each slice's declared + inferred files, not declared alone, so a step
    # that plans to touch a file its slice never declared still trips a
    # collision against another slice's overlapping write.
    combined_files = {
        sid: set(slices[sid]["files"]) | set(slices[sid]["inferred_files"])
        for sid in order
    }

    collisions: list[dict] = []
    for i, wave in enumerate(waves, 1):
        for a in range(len(wave)):
            for b in range(a + 1, len(wave)):
                shared = sorted(combined_files[wave[a]] & combined_files[wave[b]])
                for f in shared:
                    collisions.append(
                        {"wave": i, "slices": [wave[a], wave[b]], "file": f}
                    )

    # Declared-vs-inferred scope mismatches (#865 AC3) — only for slices that
    # declare slice-level Files; a slice with no declaration has nothing to
    # reconcile against.
    scope_mismatches: list[dict] = []
    for sid in order:
        declared = slices[sid]["files"]
        if not declared:
            continue
        entry = _scope_mismatch(sid, declared, slices[sid]["inferred_files"])
        if entry is not None:
            scope_mismatches.append(entry)

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
        "scope_mismatches": scope_mismatches,
    }


def main(argv: list[str] | None = None) -> int:
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
