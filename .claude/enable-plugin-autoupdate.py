#!/usr/bin/env python3
"""Enable auto-update for the dev-team plugin's marketplace, non-interactively.

Sets ``extraKnownMarketplaces.<market>.autoUpdate = true`` in the Claude Code
config ``settings.json`` so newly released plugin versions refresh at Claude Code
launch — without re-running the cloud Setup script or the SessionStart hook.

Why this exists: a Claude Code web environment snapshots its filesystem (including
``~/.claude/plugins/cache/``) and reuses it across sessions, so whatever plugin
version installs first gets pinned. ``claude plugin install`` is a no-op on an
already-installed plugin and never upgrades it. This flag — the same one the
``/plugin`` UI and the ``/upgrade`` skill toggle — makes the CLI re-pull the
marketplace and upgrade at boot, beating the snapshot freeze.

Called (best-effort) by ``.claude/cloud-setup.sh`` and
``.claude/install-dev-team.sh``. Idempotent and fail-open: it never exits
non-zero, so it can never fail a Setup script or block session start.

Stdlib only, Python 3.8+ (see ADR 0014 / 0015). Honors ``CLAUDE_CONFIG_DIR``.
"""
from __future__ import annotations

import json
import os

PLUGIN = "dev-team"


def config_dir() -> str:
    """The Claude Code config dir — CLAUDE_CONFIG_DIR if set, else ~/.claude."""
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


def run() -> None:
    cfg = config_dir()
    installed = (
        load(os.path.join(cfg, "plugins", "installed_plugins.json")) or {}
    ).get("plugins", {})
    # Resolve the marketplace id from the installed "<plugin>@<market>" key.
    market = next(
        (
            pid.split("@", 1)[1]
            for pid in installed
            if pid.split("@", 1)[0] == PLUGIN and "@" in pid
        ),
        None,
    )
    if not market:
        print(f"enable-autoupdate: '{PLUGIN}' not installed under {cfg}; nothing to do")
        return

    settings = os.path.join(cfg, "settings.json")
    data = load(settings) or {}
    ekm = data.setdefault("extraKnownMarketplaces", {})
    if market not in ekm:
        # Seed the entry from the marketplace registry so the flag has a home.
        reg = load(os.path.join(cfg, "plugins", "known_marketplaces.json")) or {}
        entry = reg.get(market)
        if not entry:
            print(
                f"enable-autoupdate: marketplace '{market}' not in registry; skipping"
            )
            return
        ekm[market] = {"source": entry["source"]}

    if ekm[market].get("autoUpdate") is True:
        print(f"enable-autoupdate: already enabled for '{market}'")
        return

    ekm[market]["autoUpdate"] = True
    tmp = settings + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, settings)
    print(f"enable-autoupdate: enabled for '{market}' in {settings}")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # fail-open: never break the calling setup/hook
        print(f"enable-autoupdate: non-fatal error: {exc}")
