#!/usr/bin/env python3
"""Deterministic SQL anti-pattern detector (#2282, #2283).

Scan mode (default)
    ``sql_anti_patterns.py [--dialect D] PATH...``
    Prints ``{"findings": [...], "errors": [...], "skipped_fragments": {...}}``.
    Exit 0 when every file was read. Exit 2 when any file could not be read;
    the other files are still scanned and reported.

Gate mode
    ``sql_anti_patterns.py --gate [--dialect D] PATH...``
    Prints ``{"status", "dispatch", "hits", "errors", "skipped_fragments"}``.
    Exits 0 once arguments parse (an argparse usage error exits 2). An
    unexpected exception becomes ``{"status": "error", "message": ...}`` with
    no traceback, so ``/code-review`` can report a detector failure instead of
    silently skipping the lens.

Paths come from the command line and from ``--files-from FILE`` (``-`` reads
standard input), one path per line. Files the detector does not handle, such
as ``README.md``, are ignored.

Each finding has ``file``, ``line``, ``rule``, ``dialect`` (the rule's dialect
tag, not the file's), ``origin``, ``severity``, ``message``, ``fix``, and
``text``.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import sql_scan
from sql_dialect import DIALECTS

EXIT_OK = 0
EXIT_FILE_ERRORS = 2


def _read_paths(args: argparse.Namespace) -> list[str]:
    paths = list(args.paths)
    if args.files_from:
        if args.files_from == "-":
            text = sys.stdin.read()
        else:
            text = Path(args.files_from).read_text(encoding="utf-8")
        paths.extend(line.strip() for line in text.splitlines() if line.strip())
    return paths


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect SQL anti-patterns.")
    parser.add_argument("paths", nargs="*", help="files to scan")
    parser.add_argument(
        "--files-from",
        help="read newline-separated paths from this file ('-' for stdin)",
    )
    parser.add_argument(
        "--dialect", choices=DIALECTS, help="force the dialect (default: infer)"
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="report whether SQL is present, for /code-review",
    )
    return parser


def _run_gate(paths: list[str], dialect: str | None) -> int:
    try:
        payload = sql_scan.gate(paths, dialect)
    except Exception as exc:  # noqa: BLE001 - the gate reports any failure as data
        payload = {"status": "error", "message": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(payload))
    return EXIT_OK


def _run_scan(paths: list[str], dialect: str | None) -> int:
    result = sql_scan.scan_paths(paths, dialect)
    print(
        json.dumps(
            {
                "findings": result.findings,
                "errors": result.errors,
                "skipped_fragments": result.skipped_fragments,
            }
        )
    )
    return EXIT_FILE_ERRORS if result.errors else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.gate:
        try:
            paths = _read_paths(args)
        except Exception as exc:  # noqa: BLE001
            print(
                json.dumps(
                    {"status": "error", "message": f"{type(exc).__name__}: {exc}"}
                )
            )
            return EXIT_OK
        return _run_gate(paths, args.dialect)
    try:
        paths = _read_paths(args)
    except (OSError, UnicodeDecodeError) as exc:
        print(
            json.dumps(
                {
                    "findings": [],
                    "errors": [f"cannot read {args.files_from}: {exc}"],
                    "skipped_fragments": {},
                }
            )
        )
        return EXIT_FILE_ERRORS
    return _run_scan(paths, args.dialect)


if __name__ == "__main__":
    raise SystemExit(main())
