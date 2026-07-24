#!/usr/bin/env python3
"""run_invariants.py — run a slice's `**Invariants:**` commands (issue #865).

Invariants are checks that must stay green *beyond* a slice's own new
acceptance tests — "don't break X" as a runnable gate term instead of tribal
knowledge. `/build`'s slice review checkpoint runs each command from the
repo root after the slice's own suite is green; a non-zero exit fails the
slice gate exactly like a red test (fix or escalate — never step over).

Each command is run in its own subshell via `shell=True` (same trust model
as the plan's own test commands — the plan author owns portability). Runs
stop at the first failure so the failing command is unambiguous.

Stdlib-only. Python 3.8+ (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import plan_parse


class InvariantResult(NamedTuple):
    command: str
    returncode: int
    stdout: str
    stderr: str


def run_invariants(commands: list[str], repo_root: str) -> list[InvariantResult]:
    """Run each command from `repo_root`, stopping at the first failure.
    Returns the results for every command actually run (in order)."""
    results: list[InvariantResult] = []
    for command in commands:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        results.append(
            InvariantResult(command, proc.returncode, proc.stdout, proc.stderr)
        )
        if proc.returncode != 0:
            break
    return results


def invariants_for_slice(plan_path: Path, slice_id: str) -> list[str]:
    """Return the parsed Invariants commands declared for `slice_id`, or
    `[]` when the slice declares none."""
    fields = plan_parse.parse_slice_optional_fields(
        plan_path.read_text(encoding="utf-8").splitlines()
    )
    entry = fields.get(slice_id)
    if not entry:
        return []
    return list(entry.get("invariants") or [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_invariants.py",
        description="Run a slice's declared Invariants commands (issue #865).",
    )
    parser.add_argument("--repo", default=".", help="Repo root to run commands from.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--plan", type=Path, help="Plan file — used with --slice to look up commands."
    )
    group.add_argument(
        "command",
        nargs="*",
        default=[],
        help="Explicit invariant command(s) to run.",
    )
    parser.add_argument("--slice", help="Slice id (required with --plan).")
    args = parser.parse_args(argv)

    if args.plan is not None:
        if not args.slice:
            parser.error("--slice is required when --plan is given")
        commands = invariants_for_slice(args.plan, args.slice)
    else:
        commands = [c for c in args.command if c]

    if not commands:
        print("No invariants declared — nothing to run.")
        return 0

    results = run_invariants(commands, args.repo)
    for result in results:
        status = "PASS" if result.returncode == 0 else "FAIL"
        print(f"[{status}] {result.command}")
        if result.returncode != 0:
            if result.stdout.strip():
                print(result.stdout)
            if result.stderr.strip():
                print(result.stderr, file=sys.stderr)

    failed = [r for r in results if r.returncode != 0]
    if failed:
        sys.stderr.write(
            f"run-invariants: invariant failed: {failed[0].command!r} "
            f"(exit {failed[0].returncode})\n"
        )
        return failed[0].returncode or 1

    print(f"All {len(results)} invariant(s) passed.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
