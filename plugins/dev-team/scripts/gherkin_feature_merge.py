#!/usr/bin/env python3
"""gherkin_feature_merge.py — merge newly-derived scenarios into an existing
.feature file without destroying prior content (issue #1420).

`gherkin-derive` used to overwrite `features/<surface>.feature` unconditionally
on every run. This module gives it a safe alternative: read the existing file,
locate the named `Feature:` block, skip any candidate scenario whose title
already exists there (exact match, trimmed), and append only genuinely-new
scenarios after the block's last existing unit — never mid-block, never
rewriting untouched text.

Two failure causes are distinguished by construction, not inferred after the
fact: `feature-not-found` (the named `Feature:` title isn't in the existing
file at all — most likely a human renamed it) and `malformed-feature-block`
(the title is found, but the block's structure can't be bounded — a dangling
`@tag` line with no following `Scenario:`, or a `Scenario Outline:` whose
`Examples:` keyword has no table rows). Both refuse to write rather than
silently corrupting or duplicating content.

Stdlib-only. Python 3.8+ (ADR 0014/0015).

Usage:
    python3 gherkin_feature_merge.py merge --existing <path> --candidates <path> \
        --feature-title "<title>" [--dry-run] [--json]
    python3 gherkin_feature_merge.py check-stale --existing <path> \
        --observed "<title>=<value>" [--observed "<title>=<value>" ...] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_FEATURE_PREFIX = "Feature:"
_BACKGROUND_PREFIX = "Background:"
_SCENARIO_PREFIXES = ("Scenario Outline:", "Scenario:")
_EXAMPLES_PREFIX = "Examples:"


@dataclass
class ScenarioUnit:
    """One `Scenario:`/`Scenario Outline:` unit — its title plus verbatim text
    (including any preceding `@tag` lines and, for an Outline, its Examples
    table) spanning from its start marker to the next unit or block end."""

    title: str
    line: int  # 1-based line number of the Scenario:/Scenario Outline: line
    text: str


@dataclass
class FeatureBlock:
    """A bounded `Feature:` block: header line, optional Background text
    (verbatim), and its ordered scenario units."""

    header_line: int  # 1-based
    background: str | None
    units: list


@dataclass
class ParseResult:
    block: object  # FeatureBlock | None
    error: object  # None | "feature-not-found" | "malformed-feature-block"


def _split_lines(text: str) -> list:
    """Split preserving original line endings so reconstruction is byte-exact."""
    return text.splitlines(keepends=True)


def _stripped(line: str) -> str:
    return line.rstrip("\r\n")


def _is_tag_line(line: str) -> bool:
    stripped = _stripped(line).strip()
    if not stripped:
        return False
    return all(tok.startswith("@") for tok in stripped.split())


def _scenario_title(line: str) -> str | None:
    """Return the title text if `line` is a Scenario:/Scenario Outline: line."""
    stripped = _stripped(line).strip()
    for prefix in _SCENARIO_PREFIXES:
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return None


def _is_unit_start(line: str) -> bool:
    return _is_tag_line(line) or _scenario_title(line) is not None


def _find_feature_header(lines: list, feature_title: str) -> int | None:
    target = feature_title.strip()
    for i, line in enumerate(lines):
        stripped = _stripped(line).strip()
        if stripped.startswith(_FEATURE_PREFIX):
            title = stripped[len(_FEATURE_PREFIX) :].strip()
            if title == target:
                return i
    return None


def _block_end(lines: list, header_index: int) -> int:
    """Index (exclusive) where the block ends: the next Feature: header
    (any title), or end of file."""
    for j in range(header_index + 1, len(lines)):
        if _stripped(lines[j]).strip().startswith(_FEATURE_PREFIX):
            return j
    return len(lines)


def _find_background(body: list) -> tuple:
    """Return (background_text_or_None, body_start_index) for the region
    of `body` before the first scenario unit."""
    for k, line in enumerate(body):
        if _stripped(line).strip().startswith(_BACKGROUND_PREFIX):
            bg_end = len(body)
            for m in range(k + 1, len(body)):
                if _is_unit_start(body[m]):
                    bg_end = m
                    break
            return "".join(body[k:bg_end]), bg_end
        if _is_unit_start(line):
            return None, k
    return None, len(body)


def _parse_units(body: list, body_start: int, header_line_no: int):
    """Parse ordered ScenarioUnits from `body[body_start:]`.

    Returns (units, None) on success, or (None, "malformed-feature-block")
    on a dangling tag line or an unterminated Scenario Outline (Examples:
    keyword present with no table rows before the unit/block ends).
    """
    units = []
    idx = body_start
    n = len(body)
    while idx < n:
        line = body[idx]
        if not _is_unit_start(line):
            idx += 1
            continue

        unit_start = idx
        scan = idx
        title = None
        title_offset = idx
        while scan < n:
            t = _scenario_title(body[scan])
            if t is not None:
                title = t
                title_offset = scan
                break
            scan += 1

        # Find where this unit ends: the next unit-start marker, or body end.
        unit_end = n
        search_from = title_offset + 1 if title is not None else unit_start + 1
        for m in range(search_from, n):
            if _is_unit_start(body[m]):
                unit_end = m
                break

        if title is None:
            # A tag line (or run of tag lines) with no following
            # Scenario:/Scenario Outline: before the block ends.
            return None, "malformed-feature-block"

        is_outline = _stripped(body[title_offset]).strip().startswith("Scenario Outline:")
        if is_outline:
            examples_idx = None
            for m in range(title_offset + 1, unit_end):
                if _stripped(body[m]).strip().startswith(_EXAMPLES_PREFIX):
                    examples_idx = m
                    break
            if examples_idx is not None:
                has_table_row = any(
                    _stripped(body[m]).strip().startswith("|")
                    for m in range(examples_idx + 1, unit_end)
                )
                if not has_table_row:
                    return None, "malformed-feature-block"

        unit_text = "".join(body[unit_start:unit_end])
        units.append(ScenarioUnit(title=title, line=header_line_no + title_offset + 1, text=unit_text))
        idx = unit_end

    return units, None


def parse_feature_block(text: str, feature_title: str) -> ParseResult:
    """Locate and bound the `Feature: <feature_title>` block in `text`.

    The "not found" check runs before any structural parse: if no `Feature:`
    header matches `feature_title` anywhere, `error="feature-not-found"` is
    returned immediately. Only once the header is located does a structural
    failure (a dangling `@tag` line, or a `Scenario Outline:` missing its
    `Examples:` table) yield `error="malformed-feature-block"`.
    """
    lines = _split_lines(text)
    header_index = _find_feature_header(lines, feature_title)
    if header_index is None:
        return ParseResult(block=None, error="feature-not-found")

    end_index = _block_end(lines, header_index)
    body = lines[header_index + 1 : end_index]

    background, body_start = _find_background(body)
    units, error = _parse_units(body, body_start, header_index + 1)
    if error is not None:
        return ParseResult(block=None, error=error)

    block = FeatureBlock(header_line=header_index + 1, background=background, units=units)
    return ParseResult(block=block, error=None)


def parse_candidate_units(text: str) -> list:
    """Parse headerless candidate scenario text (no `Feature:` wrapper) —
    the `--candidates` scratch-file shape — into ordered ScenarioUnits.
    Reuses the same unit-splitting logic `parse_feature_block` uses for the
    inside of a block, since a candidates file is exactly a block's body
    with no Background section expected."""
    body = _split_lines(text)
    units, error = _parse_units(body, 0, 0)
    if error is not None or units is None:
        return []
    return units


@dataclass
class MergeResult:
    text: str
    added_titles: list
    skipped_duplicate_titles: list
    error: object  # None | "feature-not-found" | "malformed-feature-block"


def merge_scenarios(existing_text: str, feature_title: str, candidate_units: list) -> MergeResult:
    """Append-only merge of `candidate_units` into the named Feature block.

    Relays `parse_feature_block`'s error unchanged when the block can't be
    located or bounded — this function never re-derives or guesses the
    cause. When `existing_text` is empty, synthesizes a fresh
    `Feature: <feature_title>` block containing exactly the candidates (no
    parser call needed — nothing to locate).
    """
    if not existing_text:
        header = f"Feature: {feature_title}\n\n"
        body = "".join(unit.text for unit in candidate_units)
        return MergeResult(
            text=header + body,
            added_titles=[unit.title for unit in candidate_units],
            skipped_duplicate_titles=[],
            error=None,
        )

    result = parse_feature_block(existing_text, feature_title)
    if result.error is not None:
        return MergeResult(
            text=existing_text,
            added_titles=[],
            skipped_duplicate_titles=[],
            error=result.error,
        )

    existing_titles = {unit.title.strip() for unit in result.block.units}
    new_units = [u for u in candidate_units if u.title.strip() not in existing_titles]
    skipped = [u.title for u in candidate_units if u.title.strip() in existing_titles]

    if not new_units:
        return MergeResult(
            text=existing_text, added_titles=[], skipped_duplicate_titles=skipped, error=None
        )

    lines = _split_lines(existing_text)
    header_index = _find_feature_header(lines, feature_title)
    end_index = _block_end(lines, header_index)

    insertion = "".join(unit.text for unit in new_units)
    # Insert right at the block's end boundary, preserving everything before
    # and after byte-for-byte.
    new_lines = lines[:end_index] + [insertion] + lines[end_index:]
    merged_text = "".join(new_lines)

    return MergeResult(
        text=merged_text,
        added_titles=[u.title for u in new_units],
        skipped_duplicate_titles=skipped,
        error=None,
    )


def find_then_step_text(existing_text: str, feature_title: str) -> dict:
    """Map each retained scenario's title to its verbatim `Then`/`And`-
    continuation step text (joined), for the stale-scenario check below."""
    result = parse_feature_block(existing_text, feature_title)
    if result.error is not None or result.block is None:
        return {}

    out = {}
    for unit in result.block.units:
        then_lines = []
        capturing = False
        for line in _split_lines(unit.text):
            stripped = _stripped(line).strip()
            if stripped.startswith("Then "):
                capturing = True
                then_lines.append(line)
            elif capturing and stripped.startswith("And "):
                then_lines.append(line)
            elif capturing:
                capturing = False
        out[unit.title] = "".join(then_lines)
    return out


def is_stale(then_text: str, observed_value: str) -> bool:
    """Best-effort, case-insensitive substring containment check: `False`
    (not stale) when `observed_value` appears in `then_text`, `True`
    otherwise. A scenario with no Then step (`then_text == ""`) is never
    reported stale — nothing to compare."""
    if not then_text:
        return False
    return observed_value.lower() not in then_text.lower()


def _write_error(message: str) -> None:
    sys.stderr.write(message + "\n")


def _cmd_merge(args: argparse.Namespace) -> int:
    existing_path = Path(args.existing)
    existing_text = existing_path.read_text(encoding="utf-8") if existing_path.is_file() else ""
    candidates_text = Path(args.candidates).read_text(encoding="utf-8")
    candidate_units = parse_candidate_units(candidates_text)

    result = merge_scenarios(existing_text, args.feature_title, candidate_units)

    if result.error is not None:
        if args.json:
            print(json.dumps({"written": False, "added_titles": [], "skipped_duplicate_titles": [], "error": result.error}))
        else:
            _write_error(
                f"gherkin_feature_merge: could not locate Feature: {args.feature_title!r} "
                f"in {args.existing} — no scenarios merged, existing file left untouched "
                f"(error={result.error})"
            )
        return 2

    if args.dry_run:
        if args.json:
            print(json.dumps({"written": False, "added_titles": result.added_titles, "skipped_duplicate_titles": result.skipped_duplicate_titles, "error": None}))
        else:
            sys.stdout.write(result.text)
        return 0

    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_text(result.text, encoding="utf-8")

    if args.json:
        print(json.dumps({"written": True, "added_titles": result.added_titles, "skipped_duplicate_titles": result.skipped_duplicate_titles, "error": None}))
    else:
        print(f"OK: merged {len(result.added_titles)} new scenario(s) into {args.existing}")
    return 0


def _cmd_check_stale(args: argparse.Namespace) -> int:
    existing_path = Path(args.existing)
    existing_text = existing_path.read_text(encoding="utf-8") if existing_path.is_file() else ""

    observed = {}
    for entry in args.observed:
        title, _, value = entry.partition("=")
        observed[title.strip()] = value

    then_texts = find_then_step_text(existing_text, args.feature_title)

    findings = []
    for title, value in observed.items():
        then_text = then_texts.get(title)
        if then_text is None:
            continue
        if is_stale(then_text, value):
            findings.append({"title": title, "then_text": then_text.strip(), "observed": value})

    if args.json:
        print(json.dumps({"findings": findings}))
    else:
        for f in findings:
            print(f"possibly stale: {f['title']!r} — asserts {f['then_text']!r}, code now does {f['observed']!r}")
    return 0


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gherkin_feature_merge.py")
    sub = parser.add_subparsers(dest="command", required=True)

    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("--existing", required=True)
    merge_parser.add_argument("--candidates", required=True)
    merge_parser.add_argument("--feature-title", required=True)
    merge_parser.add_argument("--dry-run", action="store_true")
    merge_parser.add_argument("--json", action="store_true")
    merge_parser.set_defaults(func=_cmd_merge)

    stale_parser = sub.add_parser("check-stale")
    stale_parser.add_argument("--existing", required=True)
    stale_parser.add_argument("--feature-title", required=True)
    stale_parser.add_argument("--observed", action="append", default=[])
    stale_parser.add_argument("--json", action="store_true")
    stale_parser.set_defaults(func=_cmd_check_stale)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
