#!/usr/bin/env python3
"""pr_close_keyword_lint.py — flag accidental issue auto-close phrasing (#977).

GitHub's closing-keyword parser pattern-matches
`(close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\\s+#\\d+`
literally, anywhere in a merged PR/commit body — it does not understand
negation. "This does not close #123" still auto-closes #123 on merge.

This script scans a drafted PR body and flags two accidental-match shapes,
never blocking:

1. A closing keyword immediately preceding an issue number, with a negation
   word (not, never, won't, doesn't, ...) earlier in the same sentence —
   the exact shape that caused #977.
2. A closing keyword match for an issue number that the body also lists
   under a non-closing `Part of #N` reference — a self-contradictory body.

Usage:
  python3 pr_close_keyword_lint.py --body-file <path> [--json]
  echo "$BODY" | python3 pr_close_keyword_lint.py [--json]

Always exits 0 (advisory only). Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass

CLOSE_RE = re.compile(
    r"\b(close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE
)
PART_OF_RE = re.compile(r"\bpart of\s+#(\d+)", re.IGNORECASE)
NEGATION_RE = re.compile(
    r"\b(not|never|no longer|won't|wont|don't|dont|doesn't|doesnt|"
    r"isn't|isnt|cannot|can't|cant)\b",
    re.IGNORECASE,
)
SENTENCE_BOUNDARY_RE = re.compile(r"[.\n]")


@dataclass
class Finding:
    issue: int
    type: str
    context: str


def _sentence_start(body: str, match_start: int) -> int:
    """Return the index just after the nearest sentence boundary before
    match_start, or 0 if none (start of body)."""
    boundary = -1
    for m in SENTENCE_BOUNDARY_RE.finditer(body, 0, match_start):
        boundary = m.end()
    return max(boundary, 0)


def find_findings(body: str) -> list[Finding]:
    part_of_issues = {int(n) for n in PART_OF_RE.findall(body)}
    findings: list[Finding] = []

    for match in CLOSE_RE.finditer(body):
        issue = int(match.group(2))
        clause_start = _sentence_start(body, match.start())
        clause = body[clause_start : match.start()]
        context = body[clause_start : match.end()].strip()

        if NEGATION_RE.search(clause):
            findings.append(
                Finding(issue=issue, type="negated-closing-keyword", context=context)
            )
        elif issue in part_of_issues:
            findings.append(
                Finding(issue=issue, type="conflicts-with-part-of", context=context)
            )

    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--body-file", help="Path to the drafted PR body")
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON")
    args = parser.parse_args(argv[1:])

    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as handle:
            body = handle.read()
    else:
        body = sys.stdin.read()

    findings = find_findings(body)

    if args.json:
        print(json.dumps({"findings": [asdict(f) for f in findings]}))
    elif findings:
        for finding in findings:
            print(
                f'warning: issue #{finding.issue} ({finding.type}): "{finding.context}"'
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
