#!/usr/bin/env python3
"""lizard --csv (stdin) -> unified-finding envelope v1 JSONL (stdout).

Consumes the CSV that ``lizard --csv <paths>`` writes — one row per function
— and emits one unified finding per *threshold breach*, so the complexity
numbers reach review agents as deterministic findings instead of being
re-derived by inference on every run (#1974).

Column order is lizard's own, positional and unheadered (verified against
lizard 1.24.0)::

    0 nloc  1 ccn  2 token  3 param  4 length  5 location
    6 file  7 name  8 long_name  9 start_line  10 end_line  [11 ns]

Column 11 appears only with the ``-Ens`` extension and is deliberately
**unused**. It is lizard's *nested-structure complexity*, not max nesting
depth (a function with three sequential one-level ``if``s scores 5 while a
two-level nested one scores 2), it is cumulative so it scales with function
size, and measured over this repo's own ``hooks/`` + ``scripts/`` tree its
median is 9 — any threshold low enough to mean "deeply nested" fires on the
majority of functions. Max nesting depth is not a metric lizard exposes; see
the lane entry in ``../references/tool-configs.md`` for what covers it
instead. A row carrying the extra column is still parsed normally.

Do not pass ``--warnings_only``: it overrides ``--csv`` and emits clang-style
text this adapter cannot read. Thresholds live in ``_CHECKS`` below, each
calibrated against that same tree so a clean file stays quiet.
"""

from __future__ import annotations

import csv
import json
import os
import sys

#: (column index, threshold, rule suffix, human label). A finding is emitted
#: when the measured value is STRICTLY greater than the threshold. Each
#: threshold sits near the 90th percentile of this repo's own functions
#: (ccn p90=11, length p95=67, param p99=6), so they flag the tail rather
#: than the middle: 10.3%, 6.1% and 1.4% of functions respectively.
_CHECKS = (
    (1, 10, "cyclomatic", "cyclomatic complexity"),
    (4, 60, "function-length", "function length in lines"),
    (3, 5, "parameter-count", "parameter count"))


def _rel(path: str) -> str:
    """Repo-relative POSIX path — the envelope forbids absolute paths."""
    text = (path or "").replace("\\", "/")
    if os.path.isabs(text):
        text = os.path.relpath(text, os.getcwd()).replace("\\", "/")
    return text.removeprefix("./")


def main(stdin=sys.stdin, stdout=sys.stdout) -> int:
    for row in csv.reader(stdin):
        if len(row) < 11:
            continue
        for index, limit, rule, label in _CHECKS:
            # One guard for every way a row can fail to yield this metric:
            # the `-Ens` column absent (IndexError) or a non-numeric cell.
            try:
                value, start, end = int(row[index]), int(row[9]), int(row[10])
            except (IndexError, ValueError):
                continue
            if value <= limit:
                continue
            stdout.write(json.dumps({
                "rule_id": f"lizard.complexity.{rule}",
                "file": _rel(row[6]),
                "line": max(start, 1),
                "end_line": max(end, start, 1),
                "severity": "warning",
                "message": f"{row[7]}: {label} is {value} (threshold {limit})",
                "metadata": {"source": "lizard", "confidence": "high",
                             "metric": rule, "value": value, "threshold": limit},
            }, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
