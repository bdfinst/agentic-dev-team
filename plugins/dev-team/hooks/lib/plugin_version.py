#!/usr/bin/env python3
"""Resolve and print the installed dev-team plugin version (#1078).

Backs the `/version` skill. Reads Claude Code's install record
(``installed_plugins.json``) and prints a single deterministic line — no
reasoning, no file-by-file searching, so the answer never depends on the model
guessing.

Resolution: a project-scoped install whose ``projectPath`` matches the current
directory wins; otherwise the user-scoped install; otherwise the first entry.

Contract:
    Output : one line, e.g. ``dev-team@bfinster v10.4.0 (scope: user)``
    Exit 0 : printed a version line
    Exit 1 : plugin not recorded as installed (stderr explains)
    Exit 2 : environment error — install record missing/malformed (stderr)

Honors ``CLAUDE_CONFIG_DIR``. Stdlib only, Python 3.8+ (ADR 0014 / 0015).
"""
from __future__ import annotations

import json
import os
import sys

PLUGIN = "dev-team"


def config_dir() -> str:
    """The Claude Code config dir — ``CLAUDE_CONFIG_DIR`` if set, else ~/.claude."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )


def _record_path(cfg: str) -> str:
    return os.path.join(cfg, "plugins", "installed_plugins.json")


def _dev_team_entries(record: dict):
    """(marketplace, entry) pairs for every dev-team install, in record order.

    Matches the plugin id ``dev-team@<marketplace>`` exactly on the name part so
    a sibling like ``aci-dev-team@…`` is never mistaken for it.
    """
    out = []
    for pid, entries in (record.get("plugins") or {}).items():
        if "@" not in pid or pid.split("@", 1)[0] != PLUGIN:
            continue
        market = pid.split("@", 1)[1]
        for entry in entries or []:
            if isinstance(entry, dict):
                out.append((market, entry))
    return out


def _select(entries, cwd: str):
    """Pick the entry that governs ``cwd``: matching project scope, else user,
    else the first available. ``entries`` is the list from ``_dev_team_entries``."""
    cwd = os.path.realpath(cwd)

    def project_match(entry: dict) -> bool:
        pp = entry.get("projectPath")
        if entry.get("scope") != "project" or not pp:
            return False
        pp = os.path.realpath(pp)
        # cwd is the project root or nested within it.
        return cwd == pp or cwd.startswith(pp + os.sep)

    for market, entry in entries:
        if project_match(entry):
            return market, entry
    for market, entry in entries:
        if entry.get("scope") == "user":
            return market, entry
    return entries[0] if entries else (None, None)


def resolve(cfg: str, cwd: str):
    """Return (line, exit_code). ``line`` is None for the non-zero exits."""
    path = _record_path(cfg)
    try:
        with open(path) as f:
            record = json.load(f)
    except FileNotFoundError:
        return None, 2
    except (json.JSONDecodeError, OSError):
        return None, 2

    entries = _dev_team_entries(record)
    if not entries:
        return None, 1

    market, entry = _select(entries, cwd)
    version = entry.get("version") or "unknown"
    scope = entry.get("scope") or "unknown"
    return f"{PLUGIN}@{market} v{version} (scope: {scope})", 0


def main(argv: list | None = None) -> int:
    cfg = config_dir()
    line, code = resolve(cfg, os.getcwd())
    if code == 0:
        print(line)
    elif code == 1:
        print(
            f"{PLUGIN} is not installed (no record in installed_plugins.json).",
            file=sys.stderr,
        )
    else:  # code == 2
        print(
            f"Environment error: cannot read the install record at {_record_path(cfg)}.",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
