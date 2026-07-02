#!/usr/bin/env python3
"""check-python-only.py — audit ADR 0014's "new scripts in Python" rule.

Enumerates any ``.sh`` files added under ``plugins/dev-team/`` in the git diff
between the branch and its base (default: ``origin/main``). Advisory today
(exit 0 + warning), promoted to a blocking gate once ADR 0014's Phase 2 is
complete.

Exclusions:
  - ``plugins/dev-team/install.sh`` — the shell-trampoline exception the ADR
    explicitly allows (needs to run before Python is guaranteed available).
  - Any file whose path matches an entry in ``AUDIT_EXCLUSIONS`` (below);
    this list is meant to shrink over time as ADR 0014's Phase 2 lands.

Usage:
    python3 scripts/check-python-only.py                    # advisory
    python3 scripts/check-python-only.py --block            # blocking mode
    python3 scripts/check-python-only.py --base origin/main # explicit base
    python3 scripts/check-python-only.py --list             # print + exit 0

Refs: ADR 0014, issue #572.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Files the ADR explicitly allows to remain shell forever.
AUDIT_EXCLUSIONS = {
    "plugins/dev-team/install.sh",
}


def _git_diff_added_files(base: str) -> list[str]:
    """Return the list of files added on the current branch vs ``base``.

    Uses ``git diff --diff-filter=A --name-only`` so only newly-added files
    are surfaced — edits to existing bash are not flagged (those are for the
    epic's phased conversion, not this audit).
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--diff-filter=A", "--name-only", f"{base}...HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        # Base ref unresolvable — surface the error but don't crash CI.
        sys.stderr.write(
            f"check-python-only: git diff against {base} failed:\n{e.stderr}"
        )
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def new_bash_scripts_in_plugin(base: str) -> list[str]:
    """Return the list of ``.sh`` files newly added under
    ``plugins/dev-team/`` in this branch's diff, minus the ADR's allowed
    exceptions.
    """
    added = _git_diff_added_files(base)
    return [
        f
        for f in added
        if f.startswith("plugins/dev-team/")
        and f.endswith(".sh")
        and f not in AUDIT_EXCLUSIONS
    ]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(
        prog="check-python-only.py",
        description=(
            "Audit for ADR 0014 — surface .sh files newly added under "
            "plugins/dev-team/. New scripts should be Python; existing bash "
            "converts per issue #572."
        ),
    )
    p.add_argument(
        "--base",
        default="origin/main",
        help="Git ref to diff against (default: origin/main)",
    )
    p.add_argument(
        "--block",
        action="store_true",
        help="Exit non-zero when violations are found (default: advisory).",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="Print the current audit exclusions list and exit 0.",
    )
    args = p.parse_args(argv)

    if args.list:
        print("check-python-only audit exclusions (ADR 0014):")
        for excl in sorted(AUDIT_EXCLUSIONS):
            print(f"  {excl}")
        return 0

    violations = new_bash_scripts_in_plugin(args.base)
    if not violations:
        return 0

    prefix = "BLOCKING" if args.block else "ADVISORY"
    sys.stderr.write(
        f"{prefix}: check-python-only found {len(violations)} newly-added "
        f".sh file(s) under plugins/dev-team/. ADR 0014 requires new scripts "
        f"to be Python:\n"
    )
    for v in violations:
        sys.stderr.write(f"  {v}\n")
    sys.stderr.write(
        "\nADR: docs/adr/0014-python-for-cross-os-scripts.md\n"
        "Epic: https://github.com/bdfinst/agentic-dev-team/issues/572\n"
    )
    return 1 if args.block else 0


if __name__ == "__main__":
    sys.exit(main())
