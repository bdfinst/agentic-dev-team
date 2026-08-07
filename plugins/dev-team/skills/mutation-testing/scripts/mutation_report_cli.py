#!/usr/bin/env python3
"""mutation_report_cli.py — CLI wrapper exposing mutation_report.py's
``survivors_by_line()`` and ``survivors_by_mutator()`` as JSON on stdout
(#1937, Step 1.4).

`mutation_report.py` is a pure, zero-I/O computation library imported by
7+ sibling scripts — it gains no argparse/`__main__` of its own. This file
is a thin, zero-domain-logic adapter (argv in, one library call, JSON out)
so an agent (`mutation-kill.md`) can invoke the computation as a tool call
instead of re-deriving it in prose, matching the CLI-wrapper shape
`mutation_exclude_policy.py` already establishes in this directory:
``import mutation_report`` (library import, no argparse in that module
itself), a ``parse_args(argv) -> argparse.Namespace`` helper, ``main(argv:
list[str] | None = None) -> int``, and flag-based dispatch (no
subparsers).

Stdlib-only. See ADR 0014.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import mutation_report


def parse_args(argv) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mutation_report_cli.py",
        description=(
            "Print mutation_report.py's survivors_by_line() or "
            "survivors_by_mutator() result as JSON on stdout."
        ),
    )
    p.add_argument(
        "--survivors-by-line",
        action="store_true",
        help="Report Survived mutants for --file, clustered by source line.",
    )
    p.add_argument(
        "--survivors-by-mutator",
        action="store_true",
        help="Report Survived mutants for --file, grouped by mutator name.",
    )
    p.add_argument("--report", required=True, metavar="PATH", help="Native mutation report path.")
    p.add_argument("--file", required=True, metavar="PATH", help="Source file to look up in the report.")
    p.add_argument(
        "--skip-static",
        action="store_true",
        help="Exclude static:true mutants — only meaningful with --survivors-by-mutator.",
    )
    return p.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)

    if args.survivors_by_line == args.survivors_by_mutator:
        sys.stderr.write(
            "error: exactly one of --survivors-by-line or --survivors-by-mutator is required\n"
        )
        return 2

    if args.skip_static and args.survivors_by_line:
        sys.stderr.write(
            "error: --skip-static is only valid with --survivors-by-mutator\n"
        )
        return 2

    report_path = Path(args.report)

    if args.survivors_by_line:
        result = mutation_report.survivors_by_line(report_path, args.file)
    else:
        if args.skip_static:
            data = mutation_report.load_report(report_path)
            if not mutation_report.static_field_present(data, args.file):
                sys.stderr.write(
                    f"skip-static: no mutant in {args.file} carries a "
                    "'static' field — skip is inapplicable\n"
                )
        result = mutation_report.survivors_by_mutator(
            report_path, args.file, skip_static=args.skip_static
        )

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
