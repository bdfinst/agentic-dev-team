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

_HOOKS_LIB_DIR = Path(__file__).resolve().parent.parent / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.append(str(_HOOKS_LIB_DIR))

from stdin_guard import read_stdin_or_exit  # type: ignore[import-not-found]

DETECTOR = _HERE / "sql_anti_patterns.py"
TIMEOUT_SECONDS = 120


def run_detector(paths: list[str], files_from: str | None) -> tuple[int, str]:
    """Run the detector gate. Returns ``(returncode, stdout)``; -1 on timeout."""
    # Read the list here: a process-substitution path such as /dev/fd/63 is
    # closed in the child, so the detector cannot open it.
    try:
        if files_from == "-":
            listed = read_stdin_or_exit("--files-from")
        elif files_from:
            listed = Path(files_from).read_text(encoding="utf-8")
        else:
            listed = ""
    except (OSError, UnicodeDecodeError):
        return -1, ""
    all_paths = paths + [line.strip() for line in listed.splitlines() if line.strip()]
    command = [sys.executable, str(DETECTOR), "--gate", *all_paths]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
            stdin=subprocess.DEVNULL,
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
