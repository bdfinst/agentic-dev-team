---
name: upgrade
description: >-
  Check for and apply plugin updates using the official Claude Code plugin
  update mechanism.
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
---

# Upgrade

Role: worker. This command updates the agentic-dev-team plugin to the latest version and ensures its marketplace is set to auto-update going forward.

You have been invoked with the `/upgrade` command.

## Steps

### 1. Read current version

Read the installed plugin's `plugin.json` to get the current version:

```bash
claude plugin list
```

Parse the output to find `agentic-dev-team` and its current version. Also read the installed `plugin.json` directly:

```
~/.claude/plugins/cache/*/agentic-dev-team/*/.claude-plugin/plugin.json
```

Report:
> **Current version**: agentic-dev-team v{version} (installed from {marketplace})

### 2. Ensure the marketplace is set to auto-update

`autoUpdate` is a **marketplace-level** flag — every plugin published by the marketplace inherits it. `settings.json` is the source of truth; Claude Code syncs the flag into the plugin registry (`known_marketplaces.json`) on the next launch or plugin operation. There is no `claude plugin` CLI flag for it, so this step edits `settings.json` directly. Running it *before* the update guarantees the flag is set even when the plugin is already up to date (step 3 may exit early).

The block resolves which marketplace `agentic-dev-team` is installed from (e.g. `bfinster`), then finds the settings scope that declares that marketplace — project (`./.claude/settings.json`), project-local (`./.claude/settings.local.json`), then user (`~/.claude/settings.json`) — and sets `autoUpdate: true` if unset. If no settings file declares it, it pulls the source from the registry and declares the marketplace (with the flag) in user settings. Idempotent: a no-op when already enabled.

```bash
python3 - <<'PY'
import json, os

PLUGIN = "agentic-dev-team"
home = os.path.expanduser("~")
cwd = os.getcwd()

def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"  ! {path} is not valid JSON ({e}); skipping")
        return None

# Resolve which marketplace this plugin is installed from (e.g. "bfinster").
installed = (load(os.path.join(home, ".claude", "plugins", "installed_plugins.json")) or {}).get("plugins", {})
market = next((pid.split("@", 1)[1] for pid in installed if pid.split("@", 1)[0] == PLUGIN and "@" in pid), None)
if not market:
    print(f"  ! Could not resolve the marketplace for '{PLUGIN}'; skipping auto-update.")
    raise SystemExit(0)

# Find the settings scope that declares the marketplace (project > local > user).
candidates = [
    os.path.join(cwd, ".claude", "settings.json"),
    os.path.join(cwd, ".claude", "settings.local.json"),
    os.path.join(home, ".claude", "settings.json"),
]
target = None
for path in candidates:
    data = load(path)
    if data and market in (data.get("extraKnownMarketplaces") or {}):
        target = [path, data]
        break

if target is None:
    # Not declared in any settings file: pull the source from the registry and
    # declare it (with autoUpdate) in user settings so the flag is durable.
    reg = load(os.path.join(home, ".claude", "plugins", "known_marketplaces.json")) or {}
    entry = reg.get(market)
    if not entry:
        print(f"  ! Marketplace '{market}' not found in settings or registry; skipping auto-update.")
        raise SystemExit(0)
    path = os.path.join(home, ".claude", "settings.json")
    data = load(path) or {}
    data.setdefault("extraKnownMarketplaces", {})[market] = {"source": entry["source"]}
    target = [path, data]

path, data = target
mk = data["extraKnownMarketplaces"][market]
if mk.get("autoUpdate") is True:
    print(f"  auto-update already enabled for '{market}' ({path})")
else:
    mk["autoUpdate"] = True
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"  enabled auto-update for '{market}' in {path}")
    print("  (takes effect on next Claude Code launch / plugin operation)")
PY
```

Report the one-line result to the user. This step never blocks the upgrade — on any "skipping" message, continue to step 3.

### 3. Run the update

```bash
claude plugin update agentic-dev-team@{marketplace}
```

Where `{marketplace}` is the marketplace name the plugin is installed from (e.g., `bfinster`).

If the command succeeds with a version change, proceed to step 4.

If the output indicates already up to date:
> Already running the latest version (v{version}).

Exit.

If the command fails, report the error and suggest:
> Update failed. You can try a manual reinstall:
> ```
> claude plugin uninstall agentic-dev-team@{marketplace}
> claude plugin install agentic-dev-team@{marketplace}
> ```

Exit.

### 4. Confirm the update

Read the new `plugin.json` to verify the version changed:

```bash
claude plugin list
```

Report:
```
## Upgrade Complete

Previous: v{old_version}
Updated:  v{new_version}

Restart Claude Code to apply the update.
```

## Notes

- The `claude plugin update` command handles fetching, caching, and version management
- Previous versions are kept for 7 days so active sessions continue working
- A restart of Claude Code is required for the new version to take effect
- Step 2 enables marketplace-level auto-update by writing `extraKnownMarketplaces.<marketplace>.autoUpdate: true` to `settings.json` (the same flag the `/plugin` UI toggles; there is no dedicated `claude plugin` CLI subcommand for it). It runs before the update so the flag is set even when the plugin is already current. With it on, routine releases land without running `/upgrade`.
