#!/usr/bin/env python3
"""Python port of scripts/build-jobs.sh (#610 / #572 Phase 3).

Resolve the effective build concurrency for a wave:

    effective = min(requested --jobs, DEV_TEAM_MAX_PARALLEL_BUILDS, wave width)

A requested value or max that is zero, negative, or non-integer clamps to 1
(deterministic, never an error). When `DEV_TEAM_MAX_PARALLEL_BUILDS` is unset,
the max defaults to a per-host ceiling `min(16, cores-2)` (floored at 1) so an
unset `--jobs` fans a wave out to its full width, bounded by the machine — the
same cap the Agent/Workflow harness uses (#1170). An explicit env value is
honored verbatim and is never re-capped by that ceiling. `--jobs 1` therefore
resolves to 1 — the sequential decision. Prints the effective integer on stdout
and a human-readable resolution line on stderr.

Usage: build_jobs.py --wave-width W [--jobs N]

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import os
import sys


def _default_max_parallel_builds(cpu_count: int | None) -> int:
    """Default `DEV_TEAM_MAX_PARALLEL_BUILDS` ceiling when the env var is unset:
    fan a wave out as wide as the machine allows, bounded by the harness's own
    concurrency cap `min(16, cores-2)` and floored at 1 (#1170). Takes the core
    count as a parameter so it is unit-testable independent of the real host —
    mirrors `default_concurrency()` in the csharp-stryker wrapper."""
    return max(1, min(16, (cpu_count or 1) - 2))


def _norm(value: str) -> int:
    """A positive integer stays; anything else (empty, 0, negative, non-numeric)
    clamps to 1 — matches the .sh's `norm()` function exactly."""
    if not value:
        return 1
    # Bash's `case '$1' in ''|*[!0-9]*) echo 1` also treats "-2" as non-numeric
    # (the leading dash is a non-digit character). Preserve that semantics.
    if not value.isdigit():
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


def main(argv: list[str]) -> int:
    jobs_raw, width_raw = _parse_argv(argv)

    # Unset env → per-host default ceiling min(16, cores-2); an explicit value
    # (even one above that ceiling) is honored verbatim by _norm (#1170).
    max_env = os.environ.get("DEV_TEAM_MAX_PARALLEL_BUILDS")
    default_max = str(_default_max_parallel_builds(os.cpu_count()))
    max_ = _norm(max_env if max_env else default_max)
    width = _norm(width_raw if width_raw else "1")
    # An unset --jobs means "as parallel as allowed": default to the max.
    jobs = _norm(jobs_raw if jobs_raw else str(max_))

    eff = jobs
    eff = min(eff, max_)
    eff = min(eff, width)

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
