#!/usr/bin/env python3
"""Calibration-floors sensor — keep knowledge/calibration-floors.json in sync
with the eval corpus and the agents/skills on disk (issue #880, slice 1 of
epic #879).

`calibration-floors.json` is the central policy table declaring the minimum
acceptable eval pass rate (`floor`, 0-1) per `riskClass` (`high|standard|
advisory`) for every fixture-bearing review agent or advisory skill. A
"fixture-bearing" target is any name that appears in an `applicableAgents` or
`applicableSkills` array under `evals/expected/*.json` AND still has a real
agent (`agents/<name>.md`) or skill (`skills/<name>/SKILL.md`) definition on
disk — a name left over in a fixture after its agent was intentionally
removed (e.g. `test-modernization-review`, retired by issue #536) is stale
fixture data, not a live calibration target, and is not required to have a
floor entry.

Three failure classes, mirroring check_registry_sync.py's MISSING/ORPHAN
shape:

  * MISSING — a fixture-bearing agent/skill has no entry in
    calibration-floors.json.
  * ORPHAN  — a calibration-floors.json entry names a target with no agent or
    skill definition on disk.
  * INVALID — an entry's `floor` is not a number in [0, 1], or its
    `riskClass` is not one of high/standard/advisory.

Keys starting with `_` (e.g. `_comment`) are metadata, not targets, and are
ignored by every check.

Exit 0 when the table is fully in sync; exit 1 with a per-discrepancy report
otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLUGIN = "plugins/dev-team"
VALID_RISK_CLASSES = {"high", "standard", "advisory"}


def disk_agent_names(root: Path) -> set:
    folder = root / PLUGIN / "agents"
    if not folder.is_dir():
        return set()
    return {p.stem for p in folder.glob("*.md")}


def disk_skill_names(root: Path) -> set:
    folder = root / PLUGIN / "skills"
    if not folder.is_dir():
        return set()
    return {p.parent.name for p in folder.glob("*/SKILL.md")}


def fixture_bearing_names(root: Path, known: set) -> set:
    """Names referenced by evals/expected/*.json applicableAgents/
    applicableSkills, restricted to names that still resolve to a real
    agent or skill on disk (see module docstring for the rationale)."""
    names = set()
    expected_dir = root / "evals" / "expected"
    if not expected_dir.is_dir():
        return names
    for path in sorted(expected_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("applicableAgents", "applicableSkills"):
            for name in data.get(key) or []:
                if name in known:
                    names.add(name)
    return names


def load_floors(root: Path) -> dict:
    path = root / PLUGIN / "knowledge" / "calibration-floors.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"calibration-floors.json is not valid JSON: {exc}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check calibration-floors.json matches the eval corpus and "
        "the agents/skills on disk."
    )
    parser.add_argument("--root", default=".", help="Repo root (default: cwd).")
    args = parser.parse_args(argv)
    root = Path(args.root)

    agents = disk_agent_names(root)
    skills = disk_skill_names(root)
    known = agents | skills

    floors = load_floors(root)
    entries = {k: v for k, v in floors.items() if not k.startswith("_")}

    required = fixture_bearing_names(root, known)

    problems = []

    missing = sorted(required - entries.keys())
    for name in missing:
        problems.append(
            f"  MISSING  floor: {name} is fixture-bearing but absent from "
            "calibration-floors.json"
        )

    orphans = sorted(name for name in entries if name not in known)
    for name in orphans:
        problems.append(
            f"  ORPHAN   floor: '{name}' has no agent or skill definition on disk"
        )

    for name in sorted(entries):
        entry = entries[name]
        if not isinstance(entry, dict):
            problems.append(f"  INVALID  floor: '{name}' entry is not an object")
            continue
        risk_class = entry.get("riskClass")
        floor_value = entry.get("floor")
        if risk_class not in VALID_RISK_CLASSES:
            problems.append(
                f"  INVALID  floor: '{name}' has unknown riskClass "
                f"'{risk_class}' (expected one of {sorted(VALID_RISK_CLASSES)})"
            )
        is_number = isinstance(floor_value, (int, float)) and not isinstance(
            floor_value, bool
        )
        if not is_number or not (0 <= floor_value <= 1):
            problems.append(
                f"  INVALID  floor: '{name}' has out-of-range or non-numeric "
                f"floor '{floor_value}' (expected a number in [0, 1])"
            )

    if problems:
        print("Calibration floors out of sync with eval corpus / disk:")
        print("\n".join(problems))
        print(
            f"\n{len(problems)} discrepancy(ies). Update "
            f"{PLUGIN}/knowledge/calibration-floors.json."
        )
        return 1

    print(
        "Calibration floors in sync: every fixture-bearing agent/skill has a "
        "valid floor entry, and every entry resolves to a real agent or skill."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
