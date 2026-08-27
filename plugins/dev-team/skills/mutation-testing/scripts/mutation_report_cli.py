#!/usr/bin/env python3
"""mutation_report_cli.py — CLI wrapper exposing mutation_report.py's
``survivors_by_line()``, ``survivors_by_mutator()``, and
``accepted_static_survivors()`` as JSON on stdout (#1937, Step 1.4; #1940
Step 2.2).

`mutation_report.py` is a pure computation library with no argparse/
`__main__` and no stdout output, imported by 7 sibling scripts — it gains
no CLI of its own. This file is a thin, zero-domain-logic adapter (argv in,
one library call, JSON out) so an agent (`mutation-kill.md`) can invoke
the computation as a tool call instead of re-deriving it in prose, matching
the CLI-wrapper shape
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
            "Print mutation_report.py's survivors_by_line(), "
            "survivors_by_mutator(), or accepted_static_survivors() "
            "result as JSON on stdout."
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
    p.add_argument(
        "--accepted-static-survivors",
        action="store_true",
        help=(
            "Report Survived+static:true mutants for --file as "
            "accepted-survivor entries."
        ),
    )
    p.add_argument("--report", required=True, metavar="PATH", help="Native mutation report path.")
    p.add_argument("--file", required=True, metavar="PATH", help="Source file to look up in the report.")
    p.add_argument(
        "--skip-static",
        action="store_true",
        help=(
            "Exclude static:true mutants from --survivors-by-mutator/"
            "--accepted-static-survivors. With --survivors-by-line, has no "
            "filtering effect on the returned clusters by design (#1948) — "
            "see survivors_by_line()'s docstring."
        ),
    )
    return p.parse_args(list(argv))


def _maybe_warn_skip_static_inapplicable(data: dict, file_path: str) -> None:
    """Print a diagnostic notice when ``--skip-static`` was requested but
    has no effect, distinguishing the two distinct causes ``has_static_field``
    collapses into one ``False`` (round-1 review, #1937): the file matched
    but no mutant in it carries a ``static`` field, versus the file never
    matched any report key at all.
    """
    if mutation_report.has_static_field(data, file_path):
        return
    if mutation_report.is_file_in_report(data, file_path):
        sys.stderr.write(
            f"skip-static: no mutant in {file_path} carries a "
            "'static' field — skip is inapplicable\n"
        )
    else:
        sys.stderr.write(
            f"skip-static: {file_path} is not present in the report — "
            "skip is inapplicable\n"
        )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)

    if (
        sum(
            [
                args.survivors_by_line,
                args.survivors_by_mutator,
                args.accepted_static_survivors,
            ]
        )
        != 1
    ):
        sys.stderr.write(
            "error: exactly one of --survivors-by-line, --survivors-by-mutator, "
            "or --accepted-static-survivors is required\n"
        )
        return 2

    report_path = Path(args.report)

    if args.survivors_by_line:
        # #1948: --skip-static is now ACCEPTED with --survivors-by-line
        # (previously rejected with exit 2) — but it has no filtering effect
        # on the returned clusters, by design (Option A: a static survivor
        # still counts toward its line's cluster weight/ranking, since it's
        # still evidence of that line's mutation density). Print a diagnostic
        # every time the combination is used, distinct from
        # _maybe_warn_skip_static_inapplicable's "no static mutant exists"
        # case below — this fires even when static mutants ARE present,
        # because the no-op is unconditional, not contingent on the report.
        if args.skip_static:
            sys.stderr.write(
                "skip-static: --survivors-by-line clustering ignores this "
                "flag by design (#1948) — every survivor, static or not, "
                "still counts toward cluster weight; check each survivor's "
                "own 'static' field before writing a test for it\n"
            )
        result = mutation_report.survivors_by_line(
            report_path, args.file, skip_static=args.skip_static
        )
    elif args.accepted_static_survivors:
        # Single load: reuse the same parsed dict for the diagnostic below
        # and the accepted-survivor computation, instead of two separate
        # load_report() calls. When --skip-static IS set, warn if it turns
        # out to be inapplicable; when it is NOT set,
        # accepted_static_survivors_from_data() unconditionally returns []
        # (skip_static_active gates it), so warn instead that the result is
        # a guaranteed no-op — silent success here is indistinguishable
        # from "no static survivors exist".
        data = mutation_report.load_report(report_path)
        if args.skip_static:
            _maybe_warn_skip_static_inapplicable(data, args.file)
        else:
            sys.stderr.write(
                "accepted-static-survivors: --skip-static was not set — "
                "no accepted entries reported; pass --skip-static when "
                "the generation run actually narrowed by it\n"
            )
        result = mutation_report.accepted_static_survivors_from_data(
            data, args.file, skip_static_active=args.skip_static
        )
    elif args.skip_static:
        # Single load: reuse the same parsed dict for the inapplicable-skip
        # diagnostic and the survivor computation, instead of the diagnostic
        # loading once and survivors_by_mutator() loading a second time.
        data = mutation_report.load_report(report_path)
        _maybe_warn_skip_static_inapplicable(data, args.file)
        result = mutation_report.survivors_by_mutator_from_data(
            data, args.file, skip_static=True
        )
    else:
        result = mutation_report.survivors_by_mutator(report_path, args.file)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
