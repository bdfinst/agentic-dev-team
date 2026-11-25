#!/usr/bin/env python3
"""Exit 0 when a pytest run's output shows it ran tests and skipped none.

Usage: pytest_ran_all.py FILE    (FILE holds the captured pytest output)

Reads the final summary line (``3 passed, 1 skipped in 0.4s``, with or without
the ``=`` banner). Exit 1 when it reports no passed test or any skipped test,
or when no summary line is found. A gate that must run every test uses this so
a skip cannot read as a pass.

Stdlib only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SUMMARY = re.compile(r"^\W*((?:\d+ [a-z]+(?:, )?)+(?: \(.*?\))?) in \d+(?:\.\d+)?s")
COUNT = re.compile(r"(\d+) ([a-z]+)")


def summary_counts(output: str) -> dict[str, int] | None:
    """Counts by outcome word from the last summary line, ``None`` when absent."""
    for line in reversed(output.splitlines()):
        match = SUMMARY.match(line.strip())
        if match:
            counts: dict[str, int] = {}
            for number, word in COUNT.findall(match.group(1)):
                counts[word] = counts.get(word, 0) + int(number)
            return counts
    return None


def ran_all(output: str) -> bool:
    counts = summary_counts(output)
    return (
        counts is not None
        and counts.get("passed", 0) >= 1
        and not counts.get("skipped", 0)
    )


def main(argv: list[str]) -> int:
    try:
        output = Path(argv[0]).read_text(encoding="utf-8", errors="replace")
    except (IndexError, OSError):
        return 1
    return 0 if ran_all(output) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
