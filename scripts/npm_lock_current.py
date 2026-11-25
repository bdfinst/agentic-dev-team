#!/usr/bin/env python3
"""Exit 0 when node_modules holds every devDependency at its locked version.

Usage: npm_lock_current.py [DIR]    (DIR defaults to the current directory)

`npm ci` deletes `node_modules` first, so callers run it only on exit 1. A
missing lockfile, a missing install, or a version mismatch all exit 1.

Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def is_current(project: Path) -> bool:
    try:
        declared = _read_json(project / "package.json").get("devDependencies", {})
        locked = _read_json(project / "package-lock.json")["packages"]
        for name in declared:
            installed = _read_json(project / "node_modules" / name / "package.json")
            if locked[f"node_modules/{name}"]["version"] != installed["version"]:
                return False
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return True


def main(argv: list[str]) -> int:
    project = Path(argv[0]) if argv else Path.cwd()
    return 0 if is_current(project) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
