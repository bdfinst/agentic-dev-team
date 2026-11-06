"""Suppression markers for the SQL anti-pattern detector.

A comment of the form ``sql-review: ignore <rule-id>`` silences one rule's
hit. The marker applies to a hit on the same line as the marker, or on the
line right after it. It names exactly one rule. Marker text inside a string
literal does not count, because only ``comment`` tokens are read.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from sql_tokenize import COMMENT, Token

MARKER_RE = re.compile(r"sql-review:\s*ignore\s+([A-Za-z0-9_.\-]+)")


def suppressions(tokens: Iterable[Token]) -> set[tuple[str, int]]:
    """Return ``{(rule_id, marker_line)}`` for every marker in a comment.

    For a block comment that spans lines, ``marker_line`` is the line that
    holds the marker text.
    """
    found: set[tuple[str, int]] = set()
    for token in tokens:
        if token.kind != COMMENT:
            continue
        for match in MARKER_RE.finditer(token.text):
            line = token.line + token.text.count("\n", 0, match.start())
            found.add((match.group(1), line))
    return found


def is_suppressed(marks: set[tuple[str, int]], rule_id: str, hit_line: int) -> bool:
    """True when a marker for ``rule_id`` sits on ``hit_line`` or the line before."""
    return (rule_id, hit_line) in marks or (rule_id, hit_line - 1) in marks
