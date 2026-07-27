#!/usr/bin/env python3
"""gherkin_analysis_coverage_gate.py — flag a surface inventory whose
`## Analysis Coverage` section skips a required analysis category
(issue #1450).

`gherkin-derive/SKILL.md` Step 2 makes in-depth codebase analysis
mandatory: every run must explicitly analyze controllers, handlers,
services, domain logic, workflows, validation rules, error handling, and
business processes — not just enumerate registered entry points. Step 5
requires the resulting surface inventory (`gherkin.md`) to record what was
found (or explicitly "none found") for each of those eight categories, so a
run that silently skipped one is detectable rather than merely asserted.
This script is that detector.

Expected inventory shape (a `## Analysis Coverage` markdown section with one
bullet per category, bold-labelled):

    ## Analysis Coverage

    - **Controllers**: <findings, or "none found in this codebase">
    - **Handlers**: ...
    - **Services**: ...
    - **Domain logic**: ...
    - **Workflows**: ...
    - **Validation rules**: ...
    - **Error handling**: ...
    - **Business processes**: ...

Mirrors `gherkin_failure_path_gate.py`'s shape: a deterministic, best-effort
heuristic over the inventory's own text — not a semantic classifier. A
category heading present with no non-placeholder content after the colon is
treated as a gap, identical to an absent heading; only literal presence of
real content (found items, or an explicit "none found" statement) satisfies
a category.

Stdlib-only. Python 3.8+ (ADR 0014/0015).

Usage:
    python3 gherkin_analysis_coverage_gate.py --file <path/to/gherkin.md> [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Canonical eight categories named by gherkin-derive/SKILL.md Step 2 — kept
# here as the single source of truth so this gate's required-category list
# can never drift from what it enforces. Step 2/Step 5's prose names these
# verbatim (issue #1450); a future category addition/rename updates this
# tuple and the SKILL.md wording together, not independently.
_REQUIRED_CATEGORIES = (
    "controllers",
    "handlers",
    "services",
    "domain logic",
    "workflows",
    "validation rules",
    "error handling",
    "business processes",
)

# Exit codes: a three-way contract, not a boolean. 2 ("gate did not run")
# is distinct from 0 (all clear) — a missing file or absent section must
# never be silently read as "nothing missing."
EXIT_OK = 0
EXIT_MISSING_CATEGORIES = 1
EXIT_GATE_DID_NOT_RUN = 2

_SECTION_HEADING = re.compile(r"^##\s+Analysis Coverage\s*$", re.IGNORECASE)
_ANY_HEADING = re.compile(r"^#{1,6}\s+")
# A bullet naming a category: "- **<label>**: <content>" (content optional —
# an empty/placeholder tail is a gap, checked separately from the match).
_BULLET = re.compile(r"^[-*]\s*\*\*(?P<label>[^*]+)\*\*\s*:\s*(?P<content>.*)$")

# Placeholder tails that read as "not actually filled in" even though a
# bullet line exists — an angle-bracket template token, or nothing at all.
_PLACEHOLDER = re.compile(r"^<.*>$")


def find_analysis_coverage_section(text: str) -> str | None:
    """Return the body text of the `## Analysis Coverage` section (between
    its heading and the next heading of any level, or EOF), or None if no
    such heading exists."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _SECTION_HEADING.match(line.strip()):
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start, len(lines)):
        if _ANY_HEADING.match(lines[i].strip()):
            end = i
            break
    return "\n".join(lines[start:end])


def parse_category_bullets(section_text: str) -> dict:
    """Return {lowercased label: content} for every `- **label**: content`
    bullet in `section_text`. Later bullets with the same (lowercased) label
    overwrite earlier ones — the inventory is expected to list each category
    once; a duplicate is a content problem for the author, not this gate."""
    entries: dict = {}
    for line in section_text.splitlines():
        match = _BULLET.match(line.strip())
        if match:
            entries[match.group("label").strip().lower()] = match.group(
                "content"
            ).strip()
    return entries


def _is_empty_or_placeholder(content: str) -> bool:
    return content == "" or bool(_PLACEHOLDER.match(content))


def find_missing_categories(entries: dict) -> list:
    """Return the required categories (in canonical order) that are absent
    from `entries`, or present but empty/placeholder."""
    missing = []
    for category in _REQUIRED_CATEGORIES:
        content = entries.get(category)
        if content is None or _is_empty_or_placeholder(content):
            missing.append(category)
    return missing


def _gate_did_not_run(message: str, as_json: bool) -> int:
    """Print `message` (JSON or WARN-prefixed text) and return the shared
    exit-2 outcome — the file-not-found and no-section-found guard clauses
    are otherwise identical except for this string."""
    if as_json:
        print(json.dumps({"missing": [], "warning": message}, indent=2))
    else:
        print(f"WARN: {message}")
    return EXIT_GATE_DID_NOT_RUN


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gherkin_analysis_coverage_gate.py",
        description=(
            "Flag a gherkin.md surface inventory whose Analysis Coverage "
            "section skips a required analysis category."
        ),
    )
    parser.add_argument("--file", dest="file", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.file.is_file():
        return _gate_did_not_run(f"{args.file} not found — gate did not run", args.json)

    text = args.file.read_text(encoding="utf-8", errors="replace")
    section_text = find_analysis_coverage_section(text)

    if section_text is None:
        return _gate_did_not_run(
            f"no '## Analysis Coverage' section found in {args.file} — gate did not run",
            args.json,
        )

    entries = parse_category_bullets(section_text)
    missing = find_missing_categories(entries)

    if args.json:
        print(json.dumps({"missing": missing}, indent=2))
        return EXIT_MISSING_CATEGORIES if missing else EXIT_OK

    if missing:
        print(
            f"FAIL: {len(missing)} analysis categor{'y' if len(missing) == 1 else 'ies'} missing from the coverage record:"
        )
        for category in missing:
            print(f"  - {category}")
        return EXIT_MISSING_CATEGORIES

    print(f"OK: all {len(_REQUIRED_CATEGORIES)} analysis categories recorded.")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
