#!/usr/bin/env python3
"""Deterministic size budget for plugins/dev-team/skills/specs/SKILL.md.

Epic #2159 caps each slice's SKILL.md delta at roughly 40 lines and expects
the file to stay meaningfully below its pre-extraction size. Both were
author judgment — exactly the class of mechanical question CLAUDE.md's
"deterministic tools over inference" rule says a script should answer, since
a model's eyeball estimate of "~40 lines" fails silently.

Two independent checks:

  since-baseline  the working tree's line count minus the recorded baseline
              must not exceed LINE_CAP. This is per-slice ONLY if the baseline
              is re-recorded at the end of each slice — run
              `specs_skill_delta.py baseline` as a slice's final action, or the
              number reported is cumulative growth since whenever it was last
              recorded and blames the newest slice for its predecessors' lines.
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
# Tracked on purpose: `.gitignore`'s bare `memory/` pattern matches at any
# depth, so a baseline under `.claude/memory/` could never be committed and the
# since-baseline check would be enforceable only on whichever machine last ran
# `baseline` — green everywhere else for the wrong reason.
BASELINE = (
    REPO_ROOT / "plugins" / "dev-team" / "skills" / "specs" / ".size-baseline.json"
)

# Size of SKILL.md before the persistence extraction (epic #2159 slice 1).
# The cumulative check exists to keep the file below this figure.
PRE_EXTRACTION_LINES = 243

# Epic #2159: "A slice whose SKILL.md delta exceeds ~40 lines should be
# re-cut before it lands." Exactly 40 is allowed; "exceeds" is strict.
LINE_CAP = 40


def line_count(path: Path) -> int:
    return len(path.read_text().splitlines())


def read_baseline() -> int | None:
    """Return the recorded line count, or None if it is missing or untrustworthy.

    A baseline recorded against a different file (left behind by a test run or
    an earlier layout) is treated as missing rather than silently accepted as
    this file's — the `file` key exists to be checked, not just written.
    """
    if not BASELINE.is_file():
        return None
    try:
        data = json.loads(BASELINE.read_text())
        recorded_for = data.get("file")
        if recorded_for is not None and recorded_for != str(
            SKILL.relative_to(REPO_ROOT)
        ):
            return None
        return int(data["lines"])
    except (ValueError, KeyError, TypeError, AttributeError):
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
            "no baseline recorded (or it was recorded against a different file) — "
            "run 'specs_skill_delta.py baseline' to record one, or the "
            "since-baseline cap cannot be enforced"
        )
    elif delta > LINE_CAP:
        failures.append(
            f"growth since baseline is {delta} lines, over the {LINE_CAP}-line cap "
            f"(baseline {baseline} -> {current}); re-cut the slice or move prose "
            "into references/. If earlier slices' lines are being counted here, "
            "the baseline was not re-recorded at the end of each slice."
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
        "line_cap": LINE_CAP,
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

    if args.command == "baseline" and args.check:
        parser.error(
            "'baseline' and --check are mutually exclusive: recording a baseline "
            "from a file that breaches the caps would launder the breach into the "
            "new normal. Run --check first, then baseline once it is green."
        )

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
            f"cap {LINE_CAP}; ceiling {PRE_EXTRACTION_LINES})"
        )
    else:
        for failure in result["failures"]:
            print(f"specs SKILL.md budget FAILED: {failure}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
