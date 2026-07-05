#!/usr/bin/env python3
"""Report or enable marketplace auto-update for the dev-team plugin.

Single source of truth for the ``extraKnownMarketplaces.<market>.autoUpdate``
flag — the same flag the ``/plugin`` UI toggles (there is no dedicated
``claude plugin`` CLI subcommand for it). With it on, the CLI re-pulls the
marketplace catalog and upgrades the plugin at launch, which is what keeps a
Claude Code web session current despite its reused filesystem snapshot pinning
the first-installed version.

Two callers share this one implementation, so the flag logic lives in exactly
one place:

* the ``/upgrade`` skill (``SKILL.md`` step 2) — runs ``--check`` to report
  status, asks the user for consent, then runs ``--enable`` only on "yes";
* the cloud bootstrap (``.claude/cloud-setup.sh`` and
  ``.claude/install-dev-team.sh``) — runs ``--enable`` directly, no consent,
  because pasting the Setup script / setting ``DEV_TEAM_CLOUD_INSTALL=1`` is
  itself the opt-in for an ephemeral cloud VM.

Modes:
  --check    Print ``enabled`` / ``disabled`` / ``unknown`` and exit (read-only).
  --enable   Set the flag to true, idempotently (the default if no mode given).

Idempotent and fail-open: ``--enable`` never exits non-zero, so it can never
break a Setup script or block session start. Honors ``CLAUDE_CONFIG_DIR``.
Stdlib only, Python 3.8+ (ADR 0014 / 0015).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional, Tuple

PLUGIN = "dev-team"


def config_dir() -> str:
    """The Claude Code config dir — ``CLAUDE_CONFIG_DIR`` if set, else ~/.claude."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )


def load(path: str):
    """Parse a JSON file, or return None if it is missing or malformed."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def resolve_market(cfg: str) -> Optional[str]:
    """The marketplace id the plugin is installed from (the ``@<market>`` half
    of its ``installed_plugins.json`` key), or None if it is not installed."""
    installed = (
        load(os.path.join(cfg, "plugins", "installed_plugins.json")) or {}
    ).get("plugins", {})
    return next(
        (
            pid.split("@", 1)[1]
            for pid in installed
            if pid.split("@", 1)[0] == PLUGIN and "@" in pid
        ),
        None,
    )


def settings_candidates(cfg: str) -> List[str]:
    """Settings files to consult, project-scoped first (mirrors the CLI/UI
    precedence), falling back to the config-dir user settings."""
    cwd = os.getcwd()
    return [
        os.path.join(cwd, ".claude", "settings.json"),
        os.path.join(cwd, ".claude", "settings.local.json"),
        os.path.join(cfg, "settings.json"),
    ]


def check(cfg: str) -> str:
    """Return ``enabled`` / ``disabled`` / ``unknown`` for the auto-update flag."""
    market = resolve_market(cfg)
    if not market:
        return "unknown"
    for path in settings_candidates(cfg):
        data = load(path)
        if data and market in (data.get("extraKnownMarketplaces") or {}):
            return "enabled" if data["extraKnownMarketplaces"][market].get(
                "autoUpdate"
            ) is True else "disabled"
    return "disabled"


def _target(cfg: str, market: str) -> Tuple[str, dict]:
    """Pick the settings file to write, seeding a fresh config-dir entry from the
    marketplace registry when no existing file already declares the market."""
    for path in settings_candidates(cfg):
        data = load(path)
        if data and market in (data.get("extraKnownMarketplaces") or {}):
            return path, data
    path = os.path.join(cfg, "settings.json")
    data = load(path) or {}
    reg = load(os.path.join(cfg, "plugins", "known_marketplaces.json")) or {}
    entry = reg.get(market)
    ekm = data.setdefault("extraKnownMarketplaces", {})
    ekm[market] = {"source": entry["source"]} if entry else {}
    return path, data


def enable(cfg: str) -> str:
    """Set the flag to true idempotently. Returns a one-line status message."""
    market = resolve_market(cfg)
    if not market:
        return f"'{PLUGIN}' not installed under {cfg}; nothing to do"
    path, data = _target(cfg, market)
    mk = data.setdefault("extraKnownMarketplaces", {}).setdefault(market, {})
    if mk.get("autoUpdate") is True:
        return f"already enabled for '{market}' ({path})"
    mk["autoUpdate"] = True
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return f"enabled for '{market}' in {path}"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Report status only.")
    group.add_argument("--enable", action="store_true", help="Enable (default).")
    args = parser.parse_args(argv)
    cfg = config_dir()
    if args.check:
        print(check(cfg))
        return 0
    # Default action is --enable; fail-open so a bootstrap never breaks.
    try:
        print(enable(cfg))
    except Exception as exc:  # noqa: BLE001 - never fail the calling setup/hook
        print(f"non-fatal error: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
