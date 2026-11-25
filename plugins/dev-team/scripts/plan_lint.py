#!/usr/bin/env python3
"""plan_lint.py — structural checks on a plan's step headings and bodies.

Run by `/plan` step 4 and `/build` preflight. Same exit-code contract as
`plan_waves.py`: 0 = clean (JSON `{"schema": "plan-lint/v1", "faults": []}`
on stdout), 2 = at least one fault (each named by step on stderr, full list
in the stdout JSON) or unreadable input.

Checks:
  step-id        a step id that is not plain dotted numbers (`1`, `1.2`).
  no-files       a step with no `**Files**:` line, or an empty one.
  line-citation  a step body citing a line (`path:12`, `path:12-20`,
                 `path#L12`) of a file an earlier step writes; the line
                 drifts before the later step reads it.
  step-count     a stated count (`**Steps**: N` before `## Slices`) that
                 differs from the number of step headings.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import plan_parse

_STEP_HEADING_RE = re.compile(r"^#{4,}\s+[Ss]tep\s+([^:\s][^:]*?)\s*:")
_ANY_HEADING_RE = re.compile(r"^#{1,4}\s")
_STEP_ID_RE = re.compile(r"^\d+(\.\d+)*$")
_STATED_COUNT_RE = re.compile(r"^\**(?:steps|step count)\**\s*:\s*\**\s*(\d+)\b", re.IGNORECASE)
_SLICES_HEADING_RE = re.compile(r"^##\s+Slices\b")
_CITATION_RE = re.compile(r"([\w./-]+\.\w+)(?::|#L)(\d+)(?:-\d+)?")
_TOKEN_SPLIT_RE = re.compile(r"[,\s]+")


def _fault(step: str, check: str, message: str) -> dict:
    return {"step": step, "check": check, "message": message}


def _split_steps(lines: list[str]) -> tuple[list[dict], int | None]:
    """Return (steps in order, stated step count or None)."""
    steps: list[dict] = []
    stated: int | None = None
    in_preamble = True
    current: dict | None = None
    for line in lines:
        if _SLICES_HEADING_RE.match(line):
            in_preamble = False
        if in_preamble and stated is None:
            match = _STATED_COUNT_RE.match(line.strip())
            if match:
                stated = int(match.group(1))
        heading = _STEP_HEADING_RE.match(line)
        if heading:
            current = {"id": heading.group(1).strip(), "body": [], "files": []}
            steps.append(current)
            continue
        if _ANY_HEADING_RE.match(line):
            current = None
            continue
        if current is None:
            continue
        files = plan_parse._FILES_RE.search(line) if "files" in line.lower() else None
        if files:
            value = plan_parse._clean_value(files.group(1))
            current["files"].extend(t for t in _TOKEN_SPLIT_RE.split(value) if t)
        else:
            current["body"].append(line)
    return steps, stated


def lint_plan(path: Path) -> list[dict]:
    lines = path.read_text().splitlines()
    steps, stated = _split_steps(lines)
    faults: list[dict] = []
    written: set[str] = set()
    for step in steps:
        sid = step["id"]
        if not _STEP_ID_RE.match(sid):
            faults.append(_fault(sid, "step-id", f"step id {sid!r} is not plain dotted numbers (for example 1.2)."))
        if not step["files"]:
            faults.append(_fault(sid, "no-files", "step names no files; add a **Files**: line."))
        for match in _CITATION_RE.finditer("\n".join(step["body"])):
            cited = match.group(1)
            if any(cited == w or w.endswith("/" + cited) or cited.endswith("/" + w) for w in written):
                faults.append(
                    _fault(
                        sid,
                        "line-citation",
                        f"cites line {match.group(0)!r} of a file an earlier step writes; "
                        "cite the symbol or section instead, the line will drift.",
                    )
                )
        written.update(step["files"])
    if stated is not None and stated != len(steps):
        faults.append(
            _fault("-", "step-count", f"plan states {stated} steps but has {len(steps)} step headings.")
        )
    return faults


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan_lint.py", description="Structural checks on a plan's steps."
    )
    parser.add_argument("plan", help="Path to the plan markdown file")
    args = parser.parse_args(argv)
    path = Path(args.plan)
    if not path.is_file():
        sys.stderr.write(f"plan-lint: no such plan file: {path}\n")
        return 2
    faults = lint_plan(path)
    print(json.dumps({"schema": "plan-lint/v1", "faults": faults}, indent=2, sort_keys=True))
    for f in faults:
        label = f"step {f['step']}" if f["step"] != "-" else "plan"
        sys.stderr.write(f"plan-lint: {label}: [{f['check']}] {f['message']}\n")
    return 2 if faults else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
