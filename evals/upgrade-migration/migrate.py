#!/usr/bin/env python3
"""Step 0 of /upgrade: migrate legacy 'agentic-*' plugin ids to their renamed
counterparts.

The body of this script is canonical. The /upgrade command body embeds the
same logic via the snippet contract in upgrade.md — if the snippet drifts
from this file, the eval runner catches it. Future renames add one entry
to LEGACY and one fixture.

Behavior contract:
- Read installed_plugins.json (path overridable via UPGRADE_INSTALLED_JSON
  for testability).
- For each plugin id whose prefix matches a LEGACY key, schedule an
  install-first-then-uninstall pair on the SAME marketplace and scope.
- The CLAUDE plugin command pattern is install --scope <scope> <new>@<mp>,
  then ONLY on success uninstall --scope <scope> <old>@<mp>.
- On install failure: stop, leave the old plugin in place, print the exact
  retry command, exit non-zero.
- On success: print one summary block and exit zero. The caller does NOT
  continue into the version-read or auto-update steps of /upgrade — the
  user is told to restart Claude Code and re-run /upgrade if they want
  auto-update.
- When no legacy ids are found, print 'No legacy plugin ids found' and
  exit zero with no scheduled commands.

Dry-run mode (UPGRADE_DRY_RUN=1) prints scheduled commands as 'WOULD RUN'
lines without executing them and assumes every install succeeds. This is
what the eval runner uses.

Sunset: remove this Step 0 after both dev-team and security-assessment
reach v2.0.0, or 2027-06-01, whichever comes first.
"""

import json
import os
import subprocess
import sys

LEGACY = {
    "agentic-dev-team": "dev-team",
    "agentic-security-assessment": "security-assessment",
}


def find_legacy_installs(installed_path):
    try:
        with open(installed_path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        print(f"  ! {installed_path} is not valid JSON ({exc}); skipping Step 0")
        return []
    matches = []
    for plugin_id in (data.get("plugins") or {}).keys():
        # plugin_id format: name@marketplace
        if "@" not in plugin_id:
            continue
        old_name, marketplace = plugin_id.split("@", 1)
        if old_name in LEGACY:
            matches.append((old_name, LEGACY[old_name], marketplace))
    return matches


def detect_scope(plugin_id, dry_run):
    """Read 'claude plugin list' and find the Scope: line for this id.
    Falls back to 'user' if not found. In dry-run mode, returns a fixed
    sentinel scope so output is deterministic for fixtures.
    """
    if dry_run:
        return "user"
    try:
        result = subprocess.run(
            ["claude", "plugin", "list"], capture_output=True, text=True, check=False
        )
        # Naive parse: find the block headed by plugin_id, then a 'Scope:' line.
        lines = result.stdout.splitlines()
        for idx, line in enumerate(lines):
            if plugin_id in line:
                for follow in lines[idx + 1 : idx + 10]:
                    if follow.strip().lower().startswith("scope:"):
                        return follow.split(":", 1)[1].strip()
                break
    except FileNotFoundError:
        pass
    return "user"


def run(cmd, dry_run):
    if dry_run:
        print("  WOULD RUN: " + " ".join(cmd))
        return 0
    print("  $ " + " ".join(cmd))
    return subprocess.run(cmd, check=False).returncode


def migrate():
    dry_run = os.environ.get("UPGRADE_DRY_RUN") == "1"
    installed_path = os.environ.get(
        "UPGRADE_INSTALLED_JSON",
        os.path.join(
            os.path.expanduser("~"), ".claude", "plugins", "installed_plugins.json"
        ),
    )

    legacy = find_legacy_installs(installed_path)
    if not legacy:
        print("No legacy plugin ids found.")
        return 0

    migrated = []
    for old, new, marketplace in legacy:
        plugin_id = f"{old}@{marketplace}"
        new_id = f"{new}@{marketplace}"
        print(f"Plugin renamed: {old} → {new}. Migrating.")
        scope = detect_scope(plugin_id, dry_run)

        install_cmd = ["claude", "plugin", "install", "--scope", scope, new_id]
        uninstall_cmd = ["claude", "plugin", "uninstall", "--scope", scope, plugin_id]

        # Install FIRST. Uninstall only on success so a failed install leaves
        # the user with the working old plugin instead of nothing.
        install_rc = run(install_cmd, dry_run)
        if install_rc != 0:
            print()
            print(f"MIGRATION FAILED — old plugin still installed.")
            print(f"Retry with: claude plugin install --scope {scope} {new_id}")
            return 1

        uninstall_rc = run(uninstall_cmd, dry_run)
        if uninstall_rc != 0:
            print()
            print(
                f"WARNING: install of {new_id} succeeded but uninstall of {plugin_id} failed."
            )
            print(f"You may have both plugins installed. Remove with:")
            print(f"  claude plugin uninstall --scope {scope} {plugin_id}")
            # Treat as partial success: the new plugin works.

        migrated.append((old, new))

    print()
    print("─── Migration Summary ───")
    for old, new in migrated:
        print(f"  {old} → {new}")
    print()
    print(
        "ACTION REQUIRED: restart Claude Code, then re-run /upgrade if you want to enable auto-update."
    )
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
