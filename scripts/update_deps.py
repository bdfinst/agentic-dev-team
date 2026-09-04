#!/usr/bin/env python3
"""update_deps.py — recursively update every real package.json in the repo.

Runs `npx npm-check-updates -u --peer` + `npm install` in the directory of every
package.json found under the repo root, skipping node_modules and eval/test
fixture trees (evals/, tests/, any `fixtures` directory). Those fixtures are
fixed test data, not live dependencies — bumping them would change what a
benchmark or content-guard test measures, not just its tooling.

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
EXCLUDED_DIR_NAMES = {"node_modules", "evals", "tests", "fixtures"}


def find_package_json_dirs() -> list[Path]:
    dirs = []
    for path in sorted(REPO_ROOT.rglob("package.json")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if EXCLUDED_DIR_NAMES.intersection(rel_parts):
            continue
        dirs.append(path.parent)
    return dirs


def update_one(directory: Path, dry_run: bool) -> bool:
    label = directory.relative_to(REPO_ROOT)
    print(f"==> {label if label != Path('.') else '.'}")
    if dry_run:
        return True
    # --peer: without it, ncu bumps typescript past typescript-eslint's peer
    # ceiling (<6.1.0) every run, so it never stays pinned.
    ncu = subprocess.run(["npx", "npm-check-updates", "-u", "--peer"], cwd=directory, check=False)
    if ncu.returncode != 0:
        return False
    install = subprocess.run(["npm", "install"], cwd=directory, check=False)
    return install.returncode == 0


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
