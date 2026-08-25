#!/usr/bin/env python3
"""jscpd JSON report (stdin) -> unified-finding envelope v1 JSONL (stdout).

Consumes the report ``jscpd --reporters json --output <dir>`` writes to
``<dir>/jscpd-report.json`` (the JSON reporter writes a file, never stdout —
verified against jscpd 5.0.16, so the lane pipes the file in) and emits one
unified finding per detected clone, anchored at the first occurrence with the
second named in the message (#1974).

The report's ``fragment`` field carries the duplicated source verbatim. It is
deliberately NOT copied into the finding: these findings are injected into
every review agent's prompt, and echoing both copies of every clone back into
that context is exactly the token cost this lane exists to remove.
"""

from __future__ import annotations

import json
import os
import sys


def _rel(path: str) -> str:
    """Repo-relative POSIX path — the envelope forbids absolute paths."""
    text = (path or "").replace("\\", "/")
    if os.path.isabs(text):
        text = os.path.relpath(text, os.getcwd()).replace("\\", "/")
    return text.removeprefix("./")


def main(stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr) -> int:
    try:
        report = json.load(stdin)
    except ValueError:
        print("WARN: jscpd report is not valid JSON — skipping", file=stderr)
        return 0
    for dup in report.get("duplicates") or [] if isinstance(report, dict) else []:
        first, second = dup.get("firstFile") or {}, dup.get("secondFile") or {}
        try:
            line = max(int(first["start"]), 1)
            end_line = max(int(first.get("end", line)), line)
            name = first["name"]
        except (KeyError, TypeError, ValueError):
            continue
        other = _rel(second.get("name") or "unknown")
        where = f"{other}:{second.get('start', '?')}-{second.get('end', '?')}"
        stdout.write(json.dumps({
            "rule_id": "jscpd.duplication.clone",
            "file": _rel(name),
            "line": line,
            "end_line": end_line,
            "severity": "warning",
            "message": (f"Duplicated block of {dup.get('lines', '?')} lines "
                        f"({dup.get('tokens', '?')} tokens) — also at {where}")[:500],
            "metadata": {"source": "jscpd", "confidence": "high",
                         "duplicate_of": other, "format": dup.get("format")},
        }, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
