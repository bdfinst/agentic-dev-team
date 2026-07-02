#!/usr/bin/env python3
"""Python port of scripts/build-worktree-baseref.sh (#587 / #572 Phase 2).

Detects the effective worktree.baseRef setting so /build can warn loudly
(never mutate) when it is not "head".

Issue #553 / plans/build-worktree-inherits-caller-head.md Slice 1.

Background: Claude Code's `worktree.baseRef: "head"` setting makes
isolation:"worktree" Agent-tool dispatch branch child worktrees from the
caller's local HEAD instead of origin/<default> ("fresh", the default).
docs/spikes/worktree-baseref-head-spike.md empirically confirmed this
setting is honored only at project (.claude/settings.json) and user
(~/.claude/settings.json) scope — NOT at project-local
(.claude/settings.local.json) or plugin (plugins/<name>/settings.json)
scope. This script's default search order reflects only the two scopes
that are actually honored.

Usage:
    build_worktree_baseref.py detect

Prints exactly one token to stdout and always exits 0
(degrade-never-abort, mirroring hooks/lib/model_resolve.py's precedent):
    head    — effective setting is "head"
    fresh   — effective setting is "fresh"
    unset   — no honored settings file sets worktree.baseRef
    unknown — detection failed — treat as fail-safe

Env vars (TEST-ONLY injection seam):
    BASEREF_SETTINGS_PATHS   colon-separated list of settings files,
                             highest precedence first. Defaults to
                             ".claude/settings.json:$HOME/.claude/settings.json".

Stdlib-only (json/os/pathlib/sys). Python 3.8+. See ADR 0014.

Refs: #572, #577, #553.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Optional


def _default_settings_paths() -> str:
    home = os.environ.get("HOME", "")
    return f".claude/settings.json:{home}/.claude/settings.json"


def _settings_paths() -> List[str]:
    raw = os.environ.get("BASEREF_SETTINGS_PATHS")
    if raw is None:
        raw = _default_settings_paths()
    # Preserve the .sh's colon-separated parsing including empty segments
    # (the `[ -n "$f" ] || continue` guard skips them).
    return [p for p in raw.split(":") if p]


def _load_worktree_baseref(path: Path) -> Optional[str]:
    """Return the .worktree.baseRef value from `path`, or None on any error.

    None distinguishes 'file unreadable or malformed' (skip to next file)
    from an empty string (parseable but no baseRef — also skip).
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    wt = data.get("worktree")
    if not isinstance(wt, dict):
        return None
    value = wt.get("baseRef")
    if not isinstance(value, str):
        return None
    return value


def _detect() -> str:
    """Walk settings files in precedence order. First honored value wins.

    Every file that fails to parse or lacks the key is skipped rather than
    aborting the whole detection. The .sh also gates on `command -v jq`;
    the .py has no such external dependency but keeps the 'unknown' exit
    reserved for future contract expansion.
    """
    for raw in _settings_paths():
        path = Path(raw)
        if not path.is_file():
            continue
        value = _load_worktree_baseref(path)
        if value == "head" or value == "fresh":
            return value
    return "unset"


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if not args or args[0] != "detect":
        # Byte-parity with the .sh's usage message: name it after the .sh
        # executable so operators searching for the exact string in logs
        # find it regardless of which implementation ran.
        sys.stderr.write("Usage: build-worktree-baseref.sh detect\n")
        return 2
    sys.stdout.write(_detect() + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
