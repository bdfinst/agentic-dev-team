#!/usr/bin/env python3
"""Python port of scripts/build-jobs.sh (#610 / #572 Phase 3).

Resolve the effective build concurrency for a wave:

    effective = min(requested --jobs, DEV_TEAM_MAX_PARALLEL_BUILDS, wave width)

A requested value or max that is zero, negative, or non-integer clamps to 1
(deterministic, never an error). Parallel fan-out is opt-in: when neither
`--jobs` nor `DEV_TEAM_MAX_PARALLEL_BUILDS` is set, the default is sequential
(effective 1) — fan-out never *saves* tokens, it trades them for wall-clock, so
it is never the silent default (#1515). An explicit `--jobs N` opts in, bounded
only by wave width; an explicit `DEV_TEAM_MAX_PARALLEL_BUILDS` opts in and is
honored verbatim (never re-capped by any per-host ceiling), with an unset
`--jobs` then fanning out to that env max. `--jobs 1` resolves to 1 — the
sequential decision. Prints the effective integer on stdout and a human-readable
resolution line on stderr.

Usage: build_jobs.py --wave-width W [--jobs N]

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import os
import sys


def _norm(value: str) -> int:
    """A positive integer stays; anything else (empty, 0, negative, non-numeric)
    clamps to 1 — matches the .sh's `norm()` function exactly, deterministic and
    never raising."""
    if not value:
        return 1
    # Require ASCII decimals. `str.isdigit()` alone is True for non-decimal
    # Unicode digits (e.g. superscript "²") that `int()` then rejects with
    # ValueError — the `isascii()` guard keeps the "never an error" contract.
    # Bash's `case '$1' in ''|*[!0-9]*) echo 1` likewise treats "-2" as
    # non-numeric (the leading dash is a non-digit character).
    if not (value.isascii() and value.isdigit()):
        return 1
    n = int(value)
    return max(n, 1)


def _parse_argv(argv: list[str]) -> tuple:
    """Return (jobs_str, width_str). Bash's arg loop: unknown flags → usage
    error + exit 2. Missing arg to a known flag reads empty (bash `${2:-}`)."""
    jobs = ""
    width = ""
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--jobs":
            jobs = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif tok == "--wave-width":
            width = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        else:
            print("usage: build-jobs.sh --wave-width W [--jobs N]", file=sys.stderr)
            sys.exit(2)
    return jobs, width


def _resolve_max(width: int, max_env: str | None) -> tuple:
    """Resolve the concurrency ceiling and report whether the env opted in. The
    env var's presence is the opt-in-to-parallel signal: set → honored verbatim
    (even above any old per-host ceiling); unset → no independent ceiling, so
    wave width alone bounds an explicit --jobs (#1515). Returns (max_, env_set)."""
    env_set = bool(max_env)
    return (_norm(max_env) if env_set else width), env_set


def _resolve_jobs(jobs_raw: str, env_set: bool, max_: int) -> int:
    """Resolve the requested job count. Default is sequential (#1515): with
    neither --jobs nor the env var set, nothing opts into fan-out, so jobs is 1.
    An explicit env with no --jobs fans to that env max; an explicit --jobs is
    honored as requested."""
    if jobs_raw:
        return _norm(jobs_raw)
    if env_set:
        return max_
    return 1


def main(argv: list[str]) -> int:
    jobs_raw, width_raw = _parse_argv(argv)

    width = _norm(width_raw if width_raw else "1")
    max_, env_set = _resolve_max(width, os.environ.get("DEV_TEAM_MAX_PARALLEL_BUILDS"))
    jobs = _resolve_jobs(jobs_raw, env_set, max_)
    eff = min(jobs, max_, width)

    # Bash: requested=${JOBS:-(unset)} — literal "(unset)" when empty.
    requested = jobs_raw if jobs_raw else "(unset)"
    print(
        f"build-jobs: requested={requested} max={max_} wave_width={width} "
        f"-> effective={eff}",
        file=sys.stderr,
    )
    print(eff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
