#!/usr/bin/env python3
"""Python port of scripts/build-wave-reconcile.sh (#612 / #572 Phase 3).

Serially merge a wave's completed slice branches into an integration branch,
then gate on the full suite before the next wave.

Order-independent: branches are merged in a deterministic (sorted) order.
Because same-wave slices touch disjoint files (build-wave.py's collision gate
guarantees it) the merged tree is identical regardless of the order slices
finished. If two branches unexpectedly touch the same file, the merge
conflicts — the script halts LOUDLY (exit 1, names the file) and **picks no
side** (it aborts the merge), starting no next-wave slice.

Usage:
  build_wave_reconcile.py --into <branch> --base <ref> [--test-cmd CMD] <slice-branch>...

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import List, Sequence


def _git(args: Sequence[str], capture: bool = True) -> subprocess.CompletedProcess:
    """Run `git <args>` with stdout+stderr captured by default."""
    return subprocess.run(
        ["git", *args],
        capture_output=capture,
        text=True,
        check=False,
    )


def _branch_exists(name: str) -> bool:
    r = _git(["rev-parse", "--verify", "--quiet", name])
    return r.returncode == 0


def _checkout_existing(into: str) -> int:
    r = _git(["checkout", into])
    if r.returncode != 0:
        print(
            f"build-wave-reconcile: cannot check out existing integration "
            f"branch '{into}'.",
            file=sys.stderr,
        )
        return 2
    return 0


def _create_from_base(into: str, base: str) -> int:
    r = _git(["checkout", "-B", into, base])
    if r.returncode != 0:
        print(
            f"build-wave-reconcile: cannot create integration branch '{into}' "
            f"from '{base}'.",
            file=sys.stderr,
        )
        return 2
    return 0


def _merge_branch(branch: str) -> int:
    r = _git(["merge", "--no-ff", "--no-edit", branch])
    if r.returncode != 0:
        # Capture conflicted paths BEFORE aborting.
        diff = _git(["diff", "--name-only", "--diff-filter=U"])
        conflicted = ", ".join(
            line for line in diff.stdout.splitlines() if line.strip()
        )
        _git(["merge", "--abort"])
        print(
            f"build-wave-reconcile: CONFLICT — same-wave branches touch "
            f"'{conflicted}'.",
            file=sys.stderr,
        )
        print(
            "  No side was chosen (merge aborted). Halting; start no next-wave slice.",
            file=sys.stderr,
        )
        return 1
    return 0


def _run_test_cmd(cmd: str) -> int:
    """Run the caller-supplied gate. Bash used `eval` with stdout+stderr
    silenced — mirror that exactly for byte-parity of the diagnostic line."""
    proc = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        print(
            f"build-wave-reconcile: full-suite gate FAILED ('{cmd}'). "
            "Halting before the next wave.",
            file=sys.stderr,
        )
        return 1
    return 0


def _parse_argv(argv: List[str]) -> argparse.Namespace | int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--into", default="")
    ap.add_argument("--base", default="")
    ap.add_argument("--test-cmd", dest="test_cmd", default="")
    ap.add_argument("branches", nargs="*")
    # Preserve the bash script's error contract: any unknown option or missing
    # required flag exits 2 with the same usage line.
    known: List[str] = []
    branches: List[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in ("--into", "--base", "--test-cmd"):
            if i + 1 >= len(argv):
                _usage()
                return 2
            known.extend([tok, argv[i + 1]])
            i += 2
        elif tok.startswith("-"):
            print(f"unknown option: {tok}", file=sys.stderr)
            return 2
        else:
            branches.append(tok)
            i += 1
    parsed = ap.parse_args(known)
    parsed.branches = branches
    if not parsed.into or not parsed.base or not parsed.branches:
        _usage()
        return 2
    return parsed


def _usage() -> None:
    # Match the .sh's exact wording (name kept as `build-wave-reconcile.sh`)
    # so bash and python emit byte-identical stderr on usage errors — the
    # parity harness gates on this.
    print(
        "usage: build-wave-reconcile.sh --into <branch> --base <ref> "
        "[--test-cmd CMD] <slice-branch>...",
        file=sys.stderr,
    )


def main(argv: List[str]) -> int:
    parsed = _parse_argv(argv)
    if isinstance(parsed, int):
        return parsed

    into: str = parsed.into
    base: str = parsed.base
    test_cmd: str = parsed.test_cmd
    branches: List[str] = parsed.branches

    # Deterministic merge order → reproducible tree regardless of caller order.
    sorted_branches = sorted(branches)

    # If $INTO exists, reconcile onto its current tip so caller WIP commits
    # (spec/plan on the integration branch made before or between waves) stay
    # in the ancestry. Only create $INTO fresh from $BASE when it does not
    # exist yet — resetting an existing $INTO to $BASE would silently discard
    # those WIP commits.
    if _branch_exists(into):
        rc = _checkout_existing(into)
    else:
        rc = _create_from_base(into, base)
    if rc != 0:
        return rc

    for branch in sorted_branches:
        rc = _merge_branch(branch)
        if rc != 0:
            return rc

    if test_cmd:
        rc = _run_test_cmd(test_cmd)
        if rc != 0:
            return rc

    # Match the .sh's exact status suffix. Bash does:
    #   suite gate ${TESTCMD:+passed}${TESTCMD:-skipped}.
    # Which expands to 'passed<TESTCMD>' when TESTCMD is set, and
    # 'skipped' when it's not. That's a shell-substitution quirk in the
    # .sh, not a spec — but byte-parity is the contract.
    gate_status = f"passed{test_cmd}" if test_cmd else "skipped"

    print(
        f"build-wave-reconcile: merged {len(sorted_branches)} slice "
        f"branch(es) into '{into}'; suite gate {gate_status}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
