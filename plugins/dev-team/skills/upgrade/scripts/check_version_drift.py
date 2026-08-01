#!/usr/bin/env python3
"""Report dev-team plugin version drift: installed version vs latest catalog.

Read-only diagnostic. Prints a one-line advisory when the installed plugin
version differs from the version the (refreshed) marketplace catalog offers.
That mismatch is the signal auto-update alone cannot surface:

* a refreshed catalog is ahead but the update lands only on the next launch, or
* the refresh was blocked (e.g. by a restrictive network policy) so the session
  is silently stale.

Prints nothing when the versions match (or when either can't be resolved), so a
caller can gate on empty output.

Modes:
  (default)         Print a plain advisory line, or nothing when current.
  --session-start   Print a SessionStart hookSpecificOutput JSON wrapping the
                    advisory, or nothing when current — for the cloud hook.

Honors ``CLAUDE_CONFIG_DIR``. Stdlib only, (ADR 0014 / 0015).
"""
from __future__ import annotations

import argparse
import json
import os

PLUGIN = "dev-team"


def config_dir() -> str:
    """The Claude Code config dir — ``CLAUDE_CONFIG_DIR`` if set, else ~/.claude."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )


def load(path: str):
    """Parse a JSON file, or return None if missing or malformed."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def installed(cfg: str) -> tuple[str | None, str | None]:
    """(version, marketplace) for the installed dev-team plugin, or (None, None)."""
    plugins = (
        load(os.path.join(cfg, "plugins", "installed_plugins.json")) or {}
    ).get("plugins", {})
    for pid, entries in plugins.items():
        if pid.split("@", 1)[0] == PLUGIN and "@" in pid and entries:
            return entries[0].get("version"), pid.split("@", 1)[1]
    return None, None


def latest(cfg: str, market: str) -> str | None:
    """The dev-team version the cached marketplace catalog offers, or None."""
    reg = load(os.path.join(cfg, "plugins", "known_marketplaces.json")) or {}
    loc = (reg.get(market) or {}).get("installLocation")
    if not loc:
        return None
    catalog = load(os.path.join(loc, ".claude-plugin", "marketplace.json")) or {}
    for p in catalog.get("plugins", []):
        if p.get("name") == PLUGIN:
            return p.get("version")
    return None


def advisory(cfg: str) -> str:
    """The drift advisory line, or '' when current / indeterminate."""
    inst, market = installed(cfg)
    if not inst or not market:
        return ""
    newest = latest(cfg, market)
    if not newest or newest == inst:
        return ""
    return (
        f"dev-team plugin is v{inst}; v{newest} is available from '{market}'. "
        "Restart Claude Code (or run /upgrade) to apply."
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Report dev-team version drift.")
    parser.add_argument(
        "--session-start",
        action="store_true",
        help="Emit a SessionStart hookSpecificOutput JSON instead of a plain line.",
    )
    args = parser.parse_args(argv)
    msg = advisory(config_dir())
    if not msg:
        return 0
    if args.session_start:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": msg,
                    }
                }
            )
        )
    else:
        print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
