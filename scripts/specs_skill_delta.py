#!/usr/bin/env python3
"""Deterministic size budget for plugins/dev-team/skills/specs/SKILL.md.

Epic #2159 caps each slice's SKILL.md delta at roughly 40 lines and expects
the file to stay meaningfully below its pre-extraction size. Both were
author judgment — exactly the class of mechanical question CLAUDE.md's
"deterministic tools over inference" rule says a script should answer, since
a model's eyeball estimate of "~40 lines" fails silently.

Two independent checks:

  per-slice   the working tree's line count minus the recorded baseline must
              not exceed PER_SLICE_LINE_CAP. Catches one slice growing the
              file past what the epic's progressive-disclosure constraint
              allows.
  cumulative  the line count must stay below PRE_EXTRACTION_LINES. Catches
              slices 2-5 each passing the per-slice cap while collectively
              re-consuming the headroom the extraction bought — the failure
              mode a per-slice cap alone cannot see.

Usage:
    specs_skill_delta.py baseline          record the current size as the baseline
    specs_skill_delta.py --check           enforce both checks (exit 1 on breach)
    specs_skill_delta.py --check --json    same, machine-readable

Stdlib only (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "specs" / "SKILL.md"
BASELINE = REPO_ROOT / ".claude" / "memory" / "specs-skill-baseline.json"

# Size of SKILL.md before the persistence extraction (epic #2159 slice 1).
# The cumulative check exists to keep the file below this figure.
PRE_EXTRACTION_LINES = 243

# Epic #2159: "A slice whose SKILL.md delta exceeds ~40 lines should be
# re-cut before it lands."
PER_SLICE_LINE_CAP = 40


def line_count(path: Path) -> int:
    return len(path.read_text().splitlines())


def read_baseline() -> int | None:
    if not BASELINE.is_file():
        return None
    try:
        return int(json.loads(BASELINE.read_text())["lines"])
    except (ValueError, KeyError, TypeError):
        return None


def write_baseline(lines: int) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(
        json.dumps(
            {"lines": lines, "file": str(SKILL.relative_to(REPO_ROOT))}, indent=2
        )
        + "\n"
    )


def evaluate() -> dict:
    current = line_count(SKILL)
    baseline = read_baseline()
    delta = None if baseline is None else current - baseline

    failures = []
    if delta is None:
        failures.append(
            "no baseline recorded — run 'specs_skill_delta.py baseline' after the "
            "extraction lands, or the per-slice cap cannot be enforced"
        )
    elif delta > PER_SLICE_LINE_CAP:
        failures.append(
            f"per-slice delta {delta} lines exceeds the {PER_SLICE_LINE_CAP}-line cap "
            f"(baseline {baseline} -> {current}); re-cut the slice or move prose into references/"
        )
    if current >= PRE_EXTRACTION_LINES:
        failures.append(
            f"cumulative size {current} lines has regressed to the pre-extraction "
            f"{PRE_EXTRACTION_LINES}-line figure; the extraction's headroom is gone"
        )

    return {
        "file": str(SKILL.relative_to(REPO_ROOT)),
        "current_lines": current,
        "baseline_lines": baseline,
        "delta_lines": delta,
        "per_slice_cap": PER_SLICE_LINE_CAP,
        "pre_extraction_lines": PRE_EXTRACTION_LINES,
        "ok": not failures,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "command",
        nargs="?",
        choices=["baseline"],
        help="record the current size as the baseline",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="enforce the per-slice and cumulative checks",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.command == "baseline":
        current = line_count(SKILL)
        write_baseline(current)
        print(f"baseline recorded: {current} lines")
        return 0

    if not args.check:
        parser.error("nothing to do — pass --check or the 'baseline' command")

    result = evaluate()
    if args.json:
        print(json.dumps(result, indent=2))
    elif result["ok"]:
        print(
            f"specs SKILL.md budget ok: {result['current_lines']} lines "
            f"(delta {result['delta_lines']:+d} vs baseline {result['baseline_lines']}, "
            f"cap {PER_SLICE_LINE_CAP}; ceiling {PRE_EXTRACTION_LINES})"
        )
    else:
        for failure in result["failures"]:
            print(f"specs SKILL.md budget FAILED: {failure}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
