#!/usr/bin/env python3
"""plan_falsifiers.py — list each plan scenario's "Still passes if:" falsifier.

Reads a plan file (draft or approved), walks each `### Slice N:` section's first fenced
gherkin block (the same walk `plan_gherkin_export.py` does), and prints one
JSON object on stdout:

    {"scenarios": [{"slice", "scenario", "falsifier"}],
     "missing": [{"slice", "scenario"}],
     "scanned_slices": [...], "skipped_slices": [...],
     "skipped_with_scenarios": [...], "error": null}

`skipped_with_scenarios` is the subset of `skipped_slices` whose section text
(fence content included) has a `Scenario:` or `Scenario Outline:` line.

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
_DOCSTRING_DELIMITERS = ('"""', "```")


def scenario_title(line: str) -> str | None:
    """Return the title when `line` starts a Scenario or Scenario Outline."""
    # stripped() removes only the line ending; strip() handles indented titles.
    text = stripped(line).strip()
    for prefix in _SCENARIO_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return None


def falsifier_text(line: str) -> str | None:
    """Return the non-empty falsifier text on `line`, else None."""
    match = FALSIFIER_RE.match(stripped(line))
    if match is None:
        return None
    return match.group(1).strip() or None


def _falsifier_after(lines: list[str], start: int) -> str | None:
    """Falsifier carried by the first non-blank line at or after `start`."""
    for i in range(start, len(lines)):
        if lines[i].strip():
            return falsifier_text(lines[i])
    return None


def scan_block(slice_id: str, gherkin: str) -> list[dict]:
    """One `{slice, scenario, falsifier}` row per scenario title in `gherkin`."""
    lines = gherkin.splitlines()
    rows = []
    in_docstring = False
    for index, line in enumerate(lines):
        if line.strip().startswith(_DOCSTRING_DELIMITERS):
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
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


def _build_report(
    scenarios: list[dict],
    scanned: list[str],
    skipped: list[str],
    skipped_with_scenarios: list[str],
    error: str | None,
) -> dict:
    """The output object; `missing` is derived from the scenarios without a falsifier."""
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
        "skipped_with_scenarios": skipped_with_scenarios,
        "error": error,
    }


def _skipped_with_scenarios(lines: list[str], skipped: list[str]) -> list[str]:
    """Ids in `skipped` whose section text holds a scenario title line."""
    return [
        slice_id
        for slice_id, _title, body in plan_parse.slice_sections(lines)
        if slice_id in skipped
        and any(scenario_title(line) is not None for line in body)
    ]


def build_falsifier_report(lines: list[str]) -> dict:
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
    return _build_report(
        scenarios, scanned, skipped, _skipped_with_scenarios(lines, skipped), None
    )


def unreadable_result(message: str) -> dict:
    """The output object for an unreadable plan: empty lists, `error` set."""
    return _build_report([], [], [], [], message)


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
    print(json.dumps(build_falsifier_report(text.split("\n")), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
