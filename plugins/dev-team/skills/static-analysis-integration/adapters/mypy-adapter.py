#!/usr/bin/env python3
"""mypy --output json (stdin) -> unified-finding envelope v1 JSONL (stdout).

Consumes the JSONL that ``mypy --output json`` (mypy >= 1.11, the first
release with the flag) writes — one JSON object per diagnostic — and emits
one unified-finding envelope per diagnostic. Older mypy rejects the flag
with a usage error; when that rejection is piped through this adapter it
degrades to a skip-with-warning (exit 0, zero findings) — never a pipeline
failure. Field mapping is documented in the Tier 3 mypy entry of
``../references/tool-configs.md``.
"""

from __future__ import annotations

import json
import sys

_SEVERITY = {"error": "error", "warning": "warning", "note": "suggestion"}
_FLAG_REJECTION_MARKERS = ("--output", "unrecognized")


def main(stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr) -> int:
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            if any(m in line.lower() for m in _FLAG_REJECTION_MARKERS):
                warn = "WARN: mypy rejected --output json (needs mypy >= 1.11)"
                print(warn + " — skipping mypy findings", file=stderr)
                return 0
            continue
        finding = {
            "rule_id": "mypy.python." + (entry.get("code") or "note"),
            "file": entry["file"],
            "line": max(int(entry["line"]), 1),
            "severity": _SEVERITY.get(entry.get("severity"), "info"),
            "message": entry["message"][:500],
            "metadata": {"source": "mypy", "confidence": "high"},
        }
        if isinstance(entry.get("column"), int) and entry["column"] >= 1:
            finding["column"] = entry["column"]
        stdout.write(json.dumps(finding, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
