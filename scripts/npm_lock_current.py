#!/usr/bin/env python3
"""Exit 0 when node_modules holds every locked package at its locked version.

Usage: npm_lock_current.py [DIR]    (DIR defaults to the current directory)

Reads every `packages` entry of `package-lock.json`, so a change to a
transitive dependency alone reads as stale. A missing `optional` or
`devOptional` entry is not stale only when it carries `os`/`cpu` limits, which
make `npm ci` skip it on a platform that does not match. `devOptional` is the
overlap of the dev and optional trees (npm's package-lock docs), so `npm ci`
installs it and a missing entry without platform limits is stale. A missing or
malformed lockfile, a missing `node_modules`, a missing required package, or a
version mismatch all exit 1.

`npm ci` deletes `node_modules` first, so callers run it only on exit 1.

Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _may_be_skipped(entry: dict) -> bool:
    """An optional entry limited to some platforms, which `npm ci` leaves out
    where they do not match."""
    optional = entry.get("optional") or entry.get("devOptional")
    return bool(optional and (entry.get("os") or entry.get("cpu")))


def _entry_is_current(project: Path, key: str, entry: dict) -> bool:
    if entry.get("link"):
        return True
    try:
        installed = _read_json(project / key / "package.json")
    except FileNotFoundError:
        return _may_be_skipped(entry)
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
