#!/usr/bin/env python3
"""update_deps.py — recursively update package.json files outside excluded trees.

Runs a pinned `npx npm-check-updates@<version> -u --peer --cooldown 3d` +
`npm install` in the directory of every package.json found under the repo
root, skipping
node_modules (any depth) and fixture trees (any depth) plus everything under
top-level evals/ and tests/. Those fixtures are fixed test data, not live
dependencies — bumping them would change what a benchmark or content-guard
test measures, not just its tooling. Only the root package.json is a live
target today; the walk exists so a second real Node project is picked up
automatically if one is ever added outside those excluded trees.

The root package.json's `update` script shells out to this so a single
`npm run update` keeps every real Node project in the repo current, not just
the root.

Usage:
  python3 scripts/update_deps.py [--dry-run]
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# evals/ and tests/ are only excluded as a top-level segment — a real Node
# project nested under some other tree happens to be named "tests" should
# still be updated. node_modules and fixtures are excluded at any depth.
TOP_LEVEL_EXCLUDED_DIRS = {"evals", "tests"}
ANY_DEPTH_EXCLUDED_DIRS = {"node_modules", "fixtures"}

SUBPROCESS_TIMEOUT_SECONDS = 600  # npm install can be slow; still needs a ceiling

# Pinned so `npx` never floats to whatever the registry serves that day —
# bump deliberately, as its own reviewed edit. Not a devDependency: ncu would
# then propose updating itself past this environment's node engine ceiling
# on every run, and --peer only checks OTHER packages' peer constraints, not
# a package's own "engines" field.
NCU_VERSION = "22.2.9"


def find_package_json_dirs() -> list[Path]:
    dirs = []
    for path in sorted(REPO_ROOT.rglob("package.json")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if rel_parts[0] in TOP_LEVEL_EXCLUDED_DIRS:
            continue
        if ANY_DEPTH_EXCLUDED_DIRS.intersection(rel_parts):
            continue
        dirs.append(path.parent)
    return dirs


def _run(cmd: list[str], directory: Path) -> bool:
    """Run cmd in directory, never raising — a missing binary or a hang both
    surface as a plain failure so the caller's failed-directory list and exit
    code stay accurate instead of an uncaught exception aborting every
    directory after this one."""
    try:
        result = subprocess.run(
            cmd, cwd=directory, check=False, timeout=SUBPROCESS_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  {' '.join(cmd)} failed: {exc}", file=sys.stderr)
        return False
    return result.returncode == 0


def update_one(directory: Path, dry_run: bool) -> bool:
    label = directory.relative_to(REPO_ROOT)
    print(f"==> {label if label != Path('.') else '.'}")
    if dry_run:
        return True
    # --peer: without it, ncu bumps typescript past typescript-eslint's peer
    # ceiling (<6.1.0, per its published peerDependencies) every run, so it
    # never stays pinned. --cooldown: skip versions published too recently to
    # have seen any real-world scrutiny.
    ncu_cmd = ["npx", "--yes", f"npm-check-updates@{NCU_VERSION}", "-u", "--peer", "--cooldown", "3d"]
    if not _run(ncu_cmd, directory):
        return False
    return _run(["npm", "install"], directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="List target directories without updating"
    )
    args = parser.parse_args()

    targets = find_package_json_dirs()
    if not targets:
        print("No package.json files found outside excluded directories.")
        return 0

    failed = [d for d in targets if not update_one(d, args.dry_run)]

    if failed:
        print("\nFailed to update:", file=sys.stderr)
        for directory in failed:
            print(f"  {directory.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
