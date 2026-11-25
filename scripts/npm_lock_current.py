#!/usr/bin/env python3
"""Exit 0 when node_modules holds every locked package at its locked version.

Usage: npm_lock_current.py [DIR]    (DIR defaults to the current directory)

Reads every `packages` entry of `package-lock.json`, so a change to a
transitive dependency alone reads as stale. An optional entry that is not
installed (a platform-specific binary) does not count as stale. A missing
lockfile, a missing `node_modules`, a missing required package, or a version
mismatch all exit 1.

`npm ci` deletes `node_modules` first, so callers run it only on exit 1.

Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _entry_is_current(project: Path, key: str, entry: dict) -> bool:
    if entry.get("link"):
        return True
    try:
        installed = _read_json(project / key / "package.json")
    except FileNotFoundError:
        return bool(entry.get("optional"))
    return installed["version"] == entry["version"]


def is_current(project: Path) -> bool:
    try:
        locked = _read_json(project / "package-lock.json")["packages"]
        if not (project / "node_modules").is_dir():
            return False
        return all(
            _entry_is_current(project, key, entry)
            for key, entry in locked.items()
            if key.startswith("node_modules/")
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def main(argv: list[str]) -> int:
    project = Path(argv[0]) if argv else Path.cwd()
    return 0 if is_current(project) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
