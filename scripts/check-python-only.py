#!/usr/bin/env python3
"""check-python-only.py — enforce ADR 0014's "new scripts in Python" rule.

Enumerates any ``.sh``/``.bats`` files newly **added** (``git diff
--diff-filter=A``) between the branch and its base (default:
``origin/main``), repo-wide, and fails the ones that fall outside an
explicit allowlist. Blocking by default (exit 1 on a violation) since ADR
0015 records the epic's Phase 3 gate as met; pass ``--advisory`` to opt back
into warn-only behavior.

Allowlist (directories and exact paths; see
docs/enforce-prefer-python-over-bash.md for the full rationale table):

  - ``plugins/dev-team/install.sh`` (exact file) — the shell trampoline that
    must run before Python is guaranteed on PATH.
  - ``plugins/security-assessment/`` (prefix) — a different plugin, shell-based
    by design; ADR 0014/0015 scope the Python rule to plugins/dev-team/ only.
  - ``tests/security-assessment/`` (prefix) — test suite for the above.
  - ``evals/`` (prefix) — eval fixtures deliberately exercise shell-script
    scenarios as test data, not shipped tooling.
  - ``.claude/cloud-setup.sh``, ``.claude/install-dev-team.sh`` (exact files)
    — same install-trampoline rationale as install.sh.
  - ``tests/lib/hermetic_tests.bats`` (exact file) — named out-of-scope-here
    in #700; owned by #677 (retire bats-core), not this gate.

Everything else repo-wide — including new repo-root ``scripts/*.sh`` — is in
scope: new additions there are blocked, not just discouraged (existing files
may still be edited; only ``--diff-filter=A`` additions are flagged).

Usage:
    python3 scripts/check-python-only.py                    # blocking (default)
    python3 scripts/check-python-only.py --advisory          # warn-only
    python3 scripts/check-python-only.py --base origin/main  # explicit base
    python3 scripts/check-python-only.py --list              # print allowlist, exit 0

Refs: ADR 0014, ADR 0015, docs/enforce-prefer-python-over-bash.md, issues #572, #700, #701, #702.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

TRACKED_EXTENSIONS = (".sh", ".bats")

# Exact file paths the allowlist exempts, one line per entry with the
# rationale inline (see the module docstring's table for detail).
ALLOWLIST_EXACT_PATHS = {
    # Shell trampoline that must run before Python is guaranteed on PATH.
    "plugins/dev-team/install.sh",
    # Cloud SessionStart / setup-script install trampolines — same rationale.
    ".claude/cloud-setup.sh",
    ".claude/install-dev-team.sh",
    # Named out-of-scope-here in #700; owned by #677 (retire bats-core).
    "tests/lib/hermetic_tests.bats",
}

# Directory prefixes the allowlist exempts wholesale (trailing "/").
ALLOWLIST_DIR_PREFIXES = (
    # A different plugin, shell-based by design (ADR 0014/0015 scope the
    # Python rule to plugins/dev-team/ only).
    "plugins/security-assessment/",
    # Test suite for the above; same rationale.
    "tests/security-assessment/",
    # Eval fixtures deliberately exercise shell-script scenarios as test
    # data, not shipped tooling.
    "evals/",
)


def _git_diff_added_files(base: str) -> list[str]:
    """Return the list of files added on the current branch vs ``base``.

    Uses ``git diff --diff-filter=A --name-only`` so only newly-added files
    are surfaced — edits to existing bash are unaffected by this gate.
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


def is_allowlisted(path: str) -> bool:
    """Return True if ``path`` is exempt from the Python-only gate."""
    if path in ALLOWLIST_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in ALLOWLIST_DIR_PREFIXES)


def find_violations(base: str) -> list[str]:
    """Return newly-added ``.sh``/``.bats`` files (repo-wide) that fall
    outside the allowlist.
    """
    added = _git_diff_added_files(base)
    return [
        f for f in added if f.endswith(TRACKED_EXTENSIONS) and not is_allowlisted(f)
    ]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(
        prog="check-python-only.py",
        description=(
            "Enforce ADR 0014 — block new .sh/.bats files added outside the "
            "allowlist, repo-wide. New scripts should be Python; existing "
            "shell converts per issue #572."
        ),
    )
    p.add_argument(
        "--base",
        default="origin/main",
        help="Git ref to diff against (default: origin/main)",
    )
    p.add_argument(
        "--advisory",
        action="store_true",
        help="Warn only, exit 0 even on violations (default: blocking).",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="Print the current allowlist and exit 0.",
    )
    args = p.parse_args(argv)

    if args.list:
        print("check-python-only allowlist (ADR 0014):")
        print("  exact paths:")
        for excl in sorted(ALLOWLIST_EXACT_PATHS):
            print(f"    {excl}")
        print("  directory prefixes:")
        for excl in sorted(ALLOWLIST_DIR_PREFIXES):
            print(f"    {excl}")
        return 0

    violations = find_violations(args.base)
    if not violations:
        return 0

    prefix = "ADVISORY" if args.advisory else "BLOCKING"
    sys.stderr.write(
        f"{prefix}: check-python-only found {len(violations)} newly-added "
        f".sh/.bats file(s) outside the allowlist. ADR 0014 requires new "
        f"scripts to be Python:\n"
    )
    for v in violations:
        sys.stderr.write(f"  {v}\n")
    sys.stderr.write(
        "\nADR: docs/adr/0014-python-for-cross-os-scripts.md\n"
        "Design doc: docs/enforce-prefer-python-over-bash.md\n"
        "Epic: https://github.com/bdfinst/agentic-dev-team/issues/572\n"
    )
    return 0 if args.advisory else 1


if __name__ == "__main__":
    sys.exit(main())
