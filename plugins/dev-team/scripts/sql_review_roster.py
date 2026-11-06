#!/usr/bin/env python3
"""Decide whether ``/code-review`` dispatches ``sql-review`` (#2283).

Runs ``sql_anti_patterns.py --gate`` over the target files and prints the
dispatch decision from ``review_roster.sql_review_decision`` as JSON:

    {"dispatch": bool, "status": "ok"|"error", "message": str,
     "hits": [...], "errors": [...], "skipped_fragments": {...},
     "dispatchFailure": null | {...}}

Always exits 0. A detector crash, a non-zero detector exit, a timeout, or
unreadable output is ``status: "error"``, never a silent skip. The caller
dispatches ``sql-review`` only when ``dispatch`` is true, passes ``hits``,
``errors``, and ``skipped_fragments`` in its context, and adds
``dispatchFailure`` to the report's ``dispatchFailures`` when it is set.

Usage: ``sql_review_roster.py [--files-from FILE|-] [PATH...]``

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import review_roster

DETECTOR = _HERE / "sql_anti_patterns.py"
TIMEOUT_SECONDS = 120


def run_detector(paths: list[str], files_from: str | None) -> tuple[int, str]:
    """Run the detector gate. Returns ``(returncode, stdout)``; -1 on timeout."""
    command = [sys.executable, str(DETECTOR), "--gate"]
    if files_from:
        command += ["--files-from", files_from]
    command += paths
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
            stdin=None if files_from == "-" else subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    return proc.returncode, proc.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Decide sql-review dispatch.")
    parser.add_argument("paths", nargs="*", help="target files")
    parser.add_argument(
        "--files-from", help="newline-separated target files ('-' for stdin)"
    )
    args = parser.parse_args(argv)
    returncode, stdout = run_detector(args.paths, args.files_from)
    print(json.dumps(review_roster.sql_review_decision(returncode, stdout)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
