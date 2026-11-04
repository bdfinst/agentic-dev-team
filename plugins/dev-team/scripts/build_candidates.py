#!/usr/bin/env python3
"""build_candidates.py — candidate lifecycle for `/build --candidates N` (#2273).

Subcommands: validate-flags, collect, rank, project, reconcile, cleanup.

Exit codes: 0 success; 1 invalid input data (message on stderr, nothing on
stdout, no file touched); 2 usage error (argparse or validate-flags).
All JSON output is `json.dumps(..., sort_keys=True)` plus one newline.

Stdlib-only. (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Sequence

EXIT_OK = 0
EXIT_INVALID_DATA = 1
EXIT_USAGE = 2

MIN_CANDIDATES = 1
MAX_CANDIDATES = 8
SPECULATIVE_MIN_CANDIDATES = 2

_ASCII_INT_RE = re.compile(r"-?[0-9]+")
_ASCII_NUMBER_RE = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


class FlagError(ValueError):
    """A `/build` flag combination that validate-flags rejects (exit 2)."""


def _fail(code: int, message: str) -> int:
    """Write one message line to stderr and return the exit code."""
    print(message, file=sys.stderr)
    return code


def _emit(payload: object) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")


def _parse_ascii_int(raw: str) -> int | None:
    return int(raw) if _ASCII_INT_RE.fullmatch(raw) else None


def _parse_candidates(raw: str) -> int:
    value = _parse_ascii_int(raw)
    if value is None or not MIN_CANDIDATES <= value <= MAX_CANDIDATES:
        raise FlagError(
            f"--candidates must be an integer between {MIN_CANDIDATES} "
            f"and {MAX_CANDIDATES}; got '{raw}'"
        )
    return value


def _parse_cost_cap(raw: str) -> float:
    value = float(raw) if _ASCII_NUMBER_RE.fullmatch(raw) else math.nan
    if not (math.isfinite(value) and value > 0):
        raise FlagError(f"--max-cost-usd must be a number greater than 0; got '{raw}'")
    return value


def validate_flags(
    candidates: str | None, max_cost_usd: str | None, jobs: str | None
) -> dict:
    """Validate the raw `/build` flag strings; raise FlagError on the first
    failure (candidates syntax, cap syntax, pairing rules, then --jobs)."""
    count = MIN_CANDIDATES if candidates is None else _parse_candidates(candidates)
    cap = None if max_cost_usd is None else _parse_cost_cap(max_cost_usd)
    speculative = count >= SPECULATIVE_MIN_CANDIDATES
    if speculative and cap is None:
        raise FlagError(
            f"--candidates N with N >= {SPECULATIVE_MIN_CANDIDATES} "
            "requires --max-cost-usd"
        )
    if cap is not None and not speculative:
        raise FlagError(
            "--max-cost-usd requires --candidates N with "
            f"N >= {SPECULATIVE_MIN_CANDIDATES}"
        )
    requested_jobs = None if jobs is None else _parse_ascii_int(jobs)
    if speculative and requested_jobs is not None and requested_jobs > 1:
        raise FlagError(
            f"--candidates N with N >= {SPECULATIVE_MIN_CANDIDATES} "
            "cannot be combined with --jobs greater than 1"
        )
    return {"candidates": count, "max_cost_usd": cap, "speculative": speculative}


def _cmd_validate_flags(args: argparse.Namespace) -> int:
    try:
        result = validate_flags(args.candidates, args.max_cost_usd, args.jobs)
    except FlagError as exc:
        return _fail(EXIT_USAGE, str(exc))
    _emit(result)
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_candidates.py", description="Candidate lifecycle for /build."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    flags = sub.add_parser("validate-flags", help="validate the raw /build flags")
    flags.add_argument("--candidates")
    flags.add_argument("--max-cost-usd")
    flags.add_argument("--jobs")
    flags.set_defaults(handler=_cmd_validate_flags)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
