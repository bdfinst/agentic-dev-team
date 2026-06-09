#!/usr/bin/env bash
# plugin-version.sh — mechanically resolve the installed version of a Claude Code
# plugin, with NO model reasoning involved.
#
# Resolution order (matches "current project first, then user settings"):
#   1. A project-scoped install whose projectPath == the current working dir.
#   2. A user-scoped (or any other-scoped) install of the same plugin.
#
# The single source of truth is ~/.claude/plugins/installed_plugins.json, which
# Claude Code maintains for every install. The on-disk plugin.json at the
# recorded installPath is preferred for the version string (it is the actual
# bytes loaded); the JSON's "version" field is the fallback.
#
# Usage:   plugin-version.sh [plugin-name]   (default: dev-team)
# Output:  one line on stdout, e.g.  dev-team@bfinster v6.7.0 (scope: user)
# Exit:    0 found, 1 not installed, 2 environment error (no python3 / no file).
set -euo pipefail

PLUGIN_NAME="${1:-dev-team}"
INSTALLED_JSON="${UPGRADE_INSTALLED_JSON:-$HOME/.claude/plugins/installed_plugins.json}"

command -v python3 >/dev/null 2>&1 || { echo "error: python3 not found" >&2; exit 2; }
[ -f "$INSTALLED_JSON" ] || { echo "error: not found: $INSTALLED_JSON" >&2; exit 2; }

PLUGIN_NAME="$PLUGIN_NAME" INSTALLED_JSON="$INSTALLED_JSON" python3 - <<'PY'
import json, os

name = os.environ["PLUGIN_NAME"]
path = os.environ["INSTALLED_JSON"]
cwd = os.path.realpath(os.getcwd())

with open(path) as f:
    plugins = (json.load(f) or {}).get("plugins", {})

# Collect every install record whose plugin id is "<name>@<marketplace>".
records = []
for pid, entries in plugins.items():
    pname = pid.split("@", 1)[0]
    market = pid.split("@", 1)[1] if "@" in pid else ""
    if pname != name:
        continue
    for e in (entries if isinstance(entries, list) else [entries]):
        records.append({
            "id": pid,
            "market": market,
            "scope": e.get("scope", ""),
            "projectPath": e.get("projectPath", ""),
            "installPath": e.get("installPath", ""),
            "version": e.get("version", ""),
        })

if not records:
    raise SystemExit(1)

def project_match(r):
    pp = r.get("projectPath") or ""
    return r["scope"] == "project" and pp and os.path.realpath(pp) == cwd

# 1. project install for THIS path  2. user scope  3. anything else.
chosen = (
    next((r for r in records if project_match(r)), None)
    or next((r for r in records if r["scope"] == "user"), None)
    or records[0]
)

# Prefer the version from the actual on-disk plugin.json at installPath.
version = chosen["version"]
manifest = os.path.join(chosen["installPath"], ".claude-plugin", "plugin.json")
try:
    with open(manifest) as f:
        version = (json.load(f) or {}).get("version", version) or version
except (OSError, json.JSONDecodeError):
    pass

scope = chosen["scope"] or "unknown"
where = "scope: project, this project" if project_match(chosen) else f"scope: {scope}"
print(f'{chosen["id"]} v{version} ({where})')
PY
