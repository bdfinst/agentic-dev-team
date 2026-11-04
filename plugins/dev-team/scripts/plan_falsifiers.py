#!/usr/bin/env python3
"""plan_falsifiers.py — list each plan scenario's "Still passes if:" falsifier.

Reads an approved plan, walks each `### Slice N:` section's first fenced
gherkin block (the same walk `plan_gherkin_export.py` does), and prints one
JSON object on stdout:

    {"scenarios": [{"slice", "scenario", "falsifier"}],
     "missing": [{"slice", "scenario"}],
     "scanned_slices": [...], "skipped_slices": [...], "error": null}

A falsifier is a `# Still passes if: <text>` comment that is the first
non-blank line under a `Scenario:` or `Scenario Outline:` title. An absent,
misplaced, wrong-case, or empty falsifier gives a null `falsifier` and a
`missing` entry. `Background:` blocks carry none and are not listed.

Exit codes: 0 for every readable plan (including one with no Gherkin); 2 when
the plan cannot be read (stdout still carries the JSON object with `error`
set, stderr the same message) or on a usage error.
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
from _gherkin_text import SCENARIO_OUTLINE_PREFIX, SCENARIO_PREFIX, stripped

FALSIFIER_PREFIX = "Still passes if:"
FALSIFIER_RE = re.compile(rf"^\s*#\s*{re.escape(FALSIFIER_PREFIX)}\s*(.*)$")

_SCENARIO_PREFIXES = (SCENARIO_OUTLINE_PREFIX, SCENARIO_PREFIX)


def scenario_title(line: str) -> str | None:
    """Return the title when `line` starts a Scenario or Scenario Outline."""
    text = stripped(line).strip()
    for prefix in _SCENARIO_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return None


def falsifier_text(line: str) -> str | None:
    """Return the non-empty falsifier text on `line`, else None."""
    match = FALSIFIER_RE.match(stripped(line))
    if match is None:
        return None
    return match.group(1).strip() or None


def _falsifier_after(lines: list[str], start: int) -> str | None:
    """Falsifier carried by the first non-blank line at or after `start`."""
    for line in lines[start:]:
        if line.strip():
            return falsifier_text(line)
    return None


def scan_block(slice_id: str, gherkin: str) -> list[dict]:
    """One `{slice, scenario, falsifier}` row per scenario title in `gherkin`."""
    lines = gherkin.splitlines()
    rows = []
    for index, line in enumerate(lines):
        title = scenario_title(line)
        if title is None:
            continue
        rows.append(
            {
                "slice": slice_id,
                "scenario": title,
                "falsifier": _falsifier_after(lines, index + 1),
            }
        )
    return rows


def falsifiers(lines: list[str]) -> dict:
    """Build the output object for a plan's lines."""
    scenarios: list[dict] = []
    scanned: list[str] = []
    skipped: list[str] = []
    for slice_id, _title, gherkin in plan_parse.slice_gherkin_blocks(lines):
        if gherkin is None:
            skipped.append(slice_id)
            continue
        scanned.append(slice_id)
        scenarios.extend(scan_block(slice_id, gherkin))
    missing = [
        {"slice": row["slice"], "scenario": row["scenario"]}
        for row in scenarios
        if row["falsifier"] is None
    ]
    return {
        "scenarios": scenarios,
        "missing": missing,
        "scanned_slices": scanned,
        "skipped_slices": skipped,
        "error": None,
    }


def unreadable_result(message: str) -> dict:
    """The output object for an unreadable plan: empty lists, `error` set."""
    return {
        "scenarios": [],
        "missing": [],
        "scanned_slices": [],
        "skipped_slices": [],
        "error": message,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan_falsifiers.py",
        description="List each plan scenario's 'Still passes if:' falsifier as JSON.",
    )
    parser.add_argument("plan", type=Path, help="Path to the plan markdown file")
    args = parser.parse_args(argv)
    try:
        text = args.plan.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        message = f"cannot read plan file: {args.plan}"
        print(json.dumps(unreadable_result(message), indent=2))
        sys.stderr.write(f"plan-falsifiers: {message}\n")
        return 2
    print(json.dumps(falsifiers(text.split("\n")), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
