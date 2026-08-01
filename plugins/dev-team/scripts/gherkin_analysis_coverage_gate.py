#!/usr/bin/env python3
"""gherkin_analysis_coverage_gate.py — flag a surface inventory whose
required-category section skips a required category.

Originally built for `gherkin-derive/SKILL.md` Step 2's mandatory in-depth
codebase analysis (issue #1450): every run must explicitly analyze
controllers, handlers, services, domain logic, workflows, validation rules,
error handling, and business processes — not just enumerate registered entry
points. Step 5 requires the resulting surface inventory (`gherkin.md`) to
record what was found (or explicitly "none found") for each of those eight
categories under a `## Analysis Coverage` (H2) heading, so a run that
silently skipped one is detectable rather than merely asserted.

Generalized (issue #1464) so the same three-way exit contract and
"missing vs. did-not-run" distinction serve a second caller,
`cd-test-architecture/SKILL.md` Step 1's own mandatory exhaustive
surface-type discovery, which records its search under a `### Components &
patterns` (H3) heading with its own eight component-pattern categories (UI,
API Provider, API Consumer, Event Consumer, Event Producer, Stateful
Service, CLI-Library, Scheduled Job). The heading level, section-header
string, and category list are now parameters (a small named-configuration
table, selected via `--config`) rather than hardcoded — the gherkin-derive
shape remains the default so its existing behavior is unchanged.

Expected inventory shape — an H-level heading (matching `--config`'s
`heading_level`) with one bullet per category, bold-labelled:

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

The "did not run" exit (2) covers three distinct shapes, all disjoint from
"nothing missing" (0) and "some categories missing" (1): the target file
is absent, the heading itself is absent, or the heading is present but has
zero recognized category rows beneath it at all (a stub section, never
actually filled in — a different claim than "N of the required categories
are genuinely missing").

Stdlib-only. (ADR 0014/0015).

Usage:
    python3 gherkin_analysis_coverage_gate.py --file <path/to/gherkin.md> [--json]
    python3 gherkin_analysis_coverage_gate.py --file <path/to/report.md> \\
        --config cd-test-architecture [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GateConfig:
    """One named configuration: which heading level and section title the
    gate looks for, and which categories are required beneath it."""

    name: str
    heading_level: int
    section_name: str
    categories: tuple[str, ...]
    # Adjective inserted before "categor(y/ies)" in the CLI's human-readable
    # FAIL/OK messages (e.g. "analysis categories", "component-pattern
    # categories") — kept per-config so gherkin-derive's existing message
    # wording ("analysis categor(y/ies)") stays byte-for-byte unchanged.
    category_kind: str = "analysis"


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

GHERKIN_DERIVE_CONFIG = GateConfig(
    name="gherkin-derive",
    heading_level=2,
    section_name="Analysis Coverage",
    categories=_REQUIRED_CATEGORIES,
)

# The eight component-pattern categories named by
# `cd-test-architecture/SKILL.md` Step 1 / `component-test-patterns.md`
# (issue #1464) — kept here as the single source of truth, same rationale
# as `_REQUIRED_CATEGORIES` above.
_CD_TEST_ARCHITECTURE_CATEGORIES = (
    "ui",
    "api provider",
    "api consumer",
    "event consumer",
    "event producer",
    "stateful service",
    "cli-library",
    "scheduled job",
)

CD_TEST_ARCHITECTURE_CONFIG = GateConfig(
    name="cd-test-architecture",
    heading_level=3,
    section_name="Components & patterns",
    categories=_CD_TEST_ARCHITECTURE_CATEGORIES,
    category_kind="component-pattern",
)

_CONFIGS = {c.name: c for c in (GHERKIN_DERIVE_CONFIG, CD_TEST_ARCHITECTURE_CONFIG)}

# Exit codes: a three-way contract, not a boolean. 2 ("gate did not run")
# is distinct from 0 (all clear) — a missing file or absent section must
# never be silently read as "nothing missing."
EXIT_OK = 0
EXIT_MISSING_CATEGORIES = 1
EXIT_GATE_DID_NOT_RUN = 2

_ANY_HEADING = re.compile(r"^#{1,6}\s+")
# A bullet naming a category: "- **<label>**: <content>" (content optional —
# an empty/placeholder tail is a gap, checked separately from the match).
_BULLET = re.compile(r"^[-*]\s*\*\*(?P<label>[^*]+)\*\*\s*:\s*(?P<content>.*)$")

# Placeholder tails that read as "not actually filled in" even though a
# bullet line exists — an angle-bracket template token, or nothing at all.
_PLACEHOLDER = re.compile(r"^<.*>$")


def _section_heading_pattern(config: GateConfig) -> re.Pattern:
    """Build the heading regex for `config`. The exact heading level is a
    real match constraint, not a hardcoded `##`: `#{level}` followed
    immediately by required whitespace means a line with more or fewer
    leading `#` characters never matches (e.g. `#{2}\\s+` cannot match
    `### Foo` — the character after the second `#` is another `#`, not
    whitespace), so an H3 config never silently matches an H2 heading or
    vice versa."""
    return re.compile(
        rf"^#{{{config.heading_level}}}\s+{re.escape(config.section_name)}\s*$",
        re.IGNORECASE,
    )


def _heading_markup(config: GateConfig) -> str:
    return f"{'#' * config.heading_level} {config.section_name}"


def find_analysis_coverage_section(
    text: str, config: GateConfig = GHERKIN_DERIVE_CONFIG
) -> str | None:
    """Return the body text of `config`'s section (between its heading and
    the next heading of any level, or EOF), or None if no such heading
    exists."""
    heading_re = _section_heading_pattern(config)
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if heading_re.match(line.strip()):
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


def find_missing_categories(
    entries: dict, config: GateConfig = GHERKIN_DERIVE_CONFIG
) -> list:
    """Return the required categories (in canonical order) that are absent
    from `entries`, or present but empty/placeholder."""
    missing = []
    for category in config.categories:
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
            "Flag a surface inventory whose required-category section "
            "skips a required category."
        ),
    )
    parser.add_argument("--file", dest="file", type=Path, required=True)
    parser.add_argument(
        "--config",
        dest="config",
        choices=sorted(_CONFIGS),
        default=GHERKIN_DERIVE_CONFIG.name,
        help=(
            "Named gate configuration (heading level, section header, "
            "category list). Defaults to gherkin-derive's existing "
            "'## Analysis Coverage' / 8-category shape."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    config = _CONFIGS[args.config]

    if not args.file.is_file():
        return _gate_did_not_run(f"{args.file} not found — gate did not run", args.json)

    text = args.file.read_text(encoding="utf-8", errors="replace")
    section_text = find_analysis_coverage_section(text, config)

    if section_text is None:
        return _gate_did_not_run(
            f"no '{_heading_markup(config)}' section found in {args.file} — gate did not run",
            args.json,
        )

    entries = parse_category_bullets(section_text)

    # A heading with zero recognized category rows beneath it (issue
    # #1464) is a third "did not run" shape, distinct from "some
    # categories missing": a section that was never filled in at all
    # (e.g. a stub heading left over from a template) is not the same
    # claim as "N of 8 categories genuinely absent" — the former means no
    # search was recorded, the latter means a partial one was.
    if not entries:
        return _gate_did_not_run(
            f"'{_heading_markup(config)}' section in {args.file} has no category rows — gate did not run",
            args.json,
        )

    missing = find_missing_categories(entries, config)

    if args.json:
        print(json.dumps({"missing": missing}, indent=2))
        return EXIT_MISSING_CATEGORIES if missing else EXIT_OK

    if missing:
        print(
            f"FAIL: {len(missing)} {config.category_kind} categor{'y' if len(missing) == 1 else 'ies'} missing from the coverage record:"
        )
        for category in missing:
            print(f"  - {category}")
        return EXIT_MISSING_CATEGORIES

    print(f"OK: all {len(config.categories)} {config.category_kind} categories recorded.")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
