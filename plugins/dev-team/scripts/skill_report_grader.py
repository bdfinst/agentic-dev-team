#!/usr/bin/env python3
"""skill_report_grader.py — deterministic grading of a skill's written report.

Two checks, both pure text and stdlib-only (ADR 0014/0015):

``grade``
    Runs a skill-report fixture's ``expected.json`` assertions over a
    generated report: ``sections_present`` (headings that must exist),
    ``sections_absent`` (headings that must not), ``regex_present`` (each
    pattern must match somewhere), ``regex_absent`` (no pattern may match).
    See ``docs/eval-system.md`` → Skill-report fixtures.

``count-targets``
    The mechanical form of the "no per-layer count target" constraint: a
    report must contain neither (a) a table whose header row has both a
    *current* column and a *recommended* or *target* column, nor (b) a
    sentence pairing a number with a test-type word (unit, component,
    contract, integration, E2E, end-to-end) and ``target``, ``should have``,
    or ``recommend``. Descriptive counts ("12 unit tests exist") are
    allowed.

Exit codes (both subcommands): 0 = pass, 1 = assertion failure(s),
2 = the check could not run (missing or unreadable input, malformed
``expected.json``). A check that cannot run is never reported as a pass.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_DID_NOT_RUN = 2

_TEST_TYPE = r"(?:unit|component|contract|integration|e2e|end-to-end)"
_NUMBER = r"\b\d+\b"
_TARGET_WORD = re.compile(r"\b(?:targets?|should have|recommend\w*)\b", re.IGNORECASE)
_NUMBER_NEAR_TYPE = re.compile(
    rf"{_NUMBER}[^.\n|]{{0,40}}?\b{_TEST_TYPE}\b|\b{_TEST_TYPE}\b[^.\n|]{{0,40}}?{_NUMBER}",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
# A list item or a bold-label field (`**Date**: ...`) starts its own block: it
# is a separate statement, not the continuation of a wrapped sentence.
_BLOCK_START = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\*\*[^*]+\*\*:)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _outside_fences(lines: list[str]) -> list[str]:
    """``lines`` with every fenced-code line replaced by an empty string, so
    positions are kept but quoted examples are never inspected."""
    kept: list[str] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            kept.append("")
        else:
            kept.append("" if in_fence else line)
    return kept


def _table_headers(lines: list[str]) -> list[list[str]]:
    """Header-row cells of every markdown table (a row followed by a
    separator row)."""
    headers: list[list[str]] = []
    for i in range(len(lines) - 1):
        row, nxt = lines[i], lines[i + 1]
        if "|" in row and _TABLE_SEPARATOR.match(nxt) and "-" in nxt:
            cells = [c.strip().lower() for c in row.strip().strip("|").split("|")]
            headers.append(cells)
    return headers


def _paragraphs(lines: list[str]) -> list[str]:
    """Prose paragraphs: consecutive non-blank lines joined, so a sentence
    wrapped across lines is checked whole. Headings and table rows end a
    paragraph and are not prose; list items and bold-label fields each start
    a new one."""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if not line.strip() or _HEADING.match(line) or "|" in line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if _BLOCK_START.match(line) and current:
            paragraphs.append(" ".join(current))
            current = []
        current.append(line.strip())
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def check_count_targets(text: str) -> list[str]:
    """Return one finding per violation of the no-count-target rule."""
    findings: list[str] = []
    lines = _outside_fences(text.splitlines())

    for cells in _table_headers(lines):
        has_current = any(re.search(r"\bcurrent\b", c) for c in cells)
        has_target = any(re.search(r"\b(?:recommend\w*|targets?)\b", c) for c in cells)
        if has_current and has_target:
            findings.append(
                "current-vs-recommended table: header row has both a current "
                f"column and a recommended/target column ({' | '.join(cells)})"
            )

    for paragraph in _paragraphs(lines):
        for sentence in _SENTENCE_SPLIT.split(paragraph):
            if _NUMBER_NEAR_TYPE.search(sentence) and _TARGET_WORD.search(sentence):
                findings.append(f"per-layer count target: {sentence.strip()}")
    return findings


def _headings(text: str) -> list[str]:
    found = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match:
            found.append(match.group(2).strip().lower())
    return found


_ASSERTION_KEYS = ("sections_present", "sections_absent", "regex_present", "regex_absent")


def validate_expected(expected: dict) -> str | None:
    """Return a reason ``expected`` cannot be run, or None when it can: each
    assertion key must hold a list of strings and every regex must compile."""
    for key in _ASSERTION_KEYS:
        value = expected.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            return f"{key} must be a list of strings"
    for key in ("regex_present", "regex_absent"):
        for pattern in expected.get(key, []):
            try:
                re.compile(pattern)
            except re.error as exc:
                return f"{key} pattern {pattern!r} does not compile: {exc}"
    return None


def grade_report(text: str, expected: dict) -> list[str]:
    """Return one failure message per unmet assertion in ``expected``."""
    failures: list[str] = []
    headings = _headings(text)

    for name in expected.get("sections_present", []):
        if name.strip().lower() not in headings:
            failures.append(f"section missing: {name}")
    for name in expected.get("sections_absent", []):
        if name.strip().lower() in headings:
            failures.append(f"section present but must be absent: {name}")
    for pattern in expected.get("regex_present", []):
        if not re.search(pattern, text, re.MULTILINE):
            failures.append(f"regex not found: {pattern}")
    for pattern in expected.get("regex_absent", []):
        if re.search(pattern, text, re.MULTILINE):
            failures.append(f"regex must be absent but matched: {pattern}")
    return failures


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"did not run: cannot read {path}: {exc}", file=sys.stderr)
        return None


def _cmd_grade(args: argparse.Namespace) -> int:
    report = _read(Path(args.report))
    raw = _read(Path(args.expected))
    if report is None or raw is None:
        return EXIT_DID_NOT_RUN
    try:
        expected = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"did not run: {args.expected} is not valid JSON: {exc}", file=sys.stderr)
        return EXIT_DID_NOT_RUN
    if not isinstance(expected, dict):
        print(f"did not run: {args.expected} must hold a JSON object", file=sys.stderr)
        return EXIT_DID_NOT_RUN

    problem = validate_expected(expected)
    if problem:
        print(f"did not run: {args.expected}: {problem}", file=sys.stderr)
        return EXIT_DID_NOT_RUN

    failures = grade_report(report, expected)
    if failures:
        print(f"FAIL: {len(failures)} assertion(s) unmet in {args.report}:")
        for failure in failures:
            print(f"  - {failure}")
        return EXIT_FAILED
    print(f"OK: {args.report} meets every assertion in {args.expected}.")
    return EXIT_OK


def _cmd_count_targets(args: argparse.Namespace) -> int:
    status = EXIT_OK
    for path in args.report:
        text = _read(Path(path))
        if text is None:
            return EXIT_DID_NOT_RUN
        findings = check_count_targets(text)
        if findings:
            status = EXIT_FAILED
            print(f"FAIL: {path}")
            for finding in findings:
                print(f"  - {finding}")
        else:
            print(f"OK: {path}")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    grade = sub.add_parser("grade", help="run a fixture's expected.json over a report")
    grade.add_argument("--report", required=True)
    grade.add_argument("--expected", required=True)
    grade.set_defaults(func=_cmd_grade)

    counts = sub.add_parser("count-targets", help="reject per-layer count targets")
    counts.add_argument("report", nargs="+")
    counts.set_defaults(func=_cmd_count_targets)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
