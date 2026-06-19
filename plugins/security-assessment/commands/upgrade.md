---
name: upgrade
description: >-
  Check for and apply security-assessment plugin updates using the
  official Claude Code plugin update mechanism.
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
---

# Upgrade

Role: worker. This command updates the security-assessment plugin to
the latest version and ensures its marketplace is set to auto-update
going forward.

You have been invoked with the `/upgrade` command.

## Steps

### 1. Read current version

```bash
claude plugin list
```

Parse the output to find `security-assessment` and its current version.
Also read the installed `plugin.json` directly:

```
~/.claude/plugins/cache/*/security-assessment/*/.claude-plugin/plugin.json
```

Report:

> **Current version**: security-assessment v{version} (installed from {marketplace})

### 2. Check auto-update status and ask the user

First, check the current auto-update status by running the script below
and reporting it to the user.

```bash
python3 - <<'PY'
import json, os

PLUGIN = "security-assessment"
home = os.path.expanduser("~")
cwd = os.getcwd()

def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"unknown ({path} is not valid JSON)")
        raise SystemExit(0)

installed = (load(os.path.join(home, ".claude", "plugins", "installed_plugins.json")) or {}).get("plugins", {})
market = next((pid.split("@", 1)[1] for pid in installed if pid.split("@", 1)[0] == PLUGIN and "@" in pid), None)
if not market:
    print("unknown (marketplace not found)")
    raise SystemExit(0)

candidates = [
    os.path.join(cwd, ".claude", "settings.json"),
    os.path.join(cwd, ".claude", "settings.local.json"),
    os.path.join(home, ".claude", "settings.json"),
]
for path in candidates:
    data = load(path)
    if data and market in (data.get("extraKnownMarketplaces") or {}):
        flag = data["extraKnownMarketplaces"][market].get("autoUpdate")
        print("enabled" if flag is True else "disabled")
        raise SystemExit(0)

print("disabled")
PY
```

Then ask the user:

> Auto-update for the `{marketplace}` marketplace is currently **{enabled/disabled}**.
> Would you like to enable auto-update so future releases install automatically? (yes/no)
>
> Note: this flag is **marketplace-level** and affects every plugin
> published from `{marketplace}` — including the companion dev-team
> plugin if you have it installed.

Wait for the user's answer before continuing. If they say **yes**, run
the enable block below. If they say **no**, skip to step 3.

**Enable block** (run only if the user consents):

```bash
python3 - <<'PY'
import json, os

PLUGIN = "security-assessment"
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

installed = (load(os.path.join(home, ".claude", "plugins", "installed_plugins.json")) or {}).get("plugins", {})
market = next((pid.split("@", 1)[1] for pid in installed if pid.split("@", 1)[0] == PLUGIN and "@" in pid), None)
if not market:
    print(f"  ! Could not resolve the marketplace for '{PLUGIN}'; skipping.")
    raise SystemExit(0)

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
    reg = load(os.path.join(home, ".claude", "plugins", "known_marketplaces.json")) or {}
    entry = reg.get(market)
    if not entry:
        print(f"  ! Marketplace '{market}' not found in settings or registry; skipping.")
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

Report the one-line result to the user, then continue to step 3.

### 3. Run the update

First, determine the install scope from `claude plugin list` output
(the `Scope:` line for `security-assessment`). It will be one of:
`user`, `project`, `local`, `managed`.

```bash
claude plugin update --scope {scope} security-assessment@{marketplace}
```

Where `{scope}` is the detected install scope (e.g., `project`) and
`{marketplace}` is the marketplace name (e.g., `bfinster`). The
`--scope` flag is required — the CLI defaults to `user`, which will
fail if the plugin is installed at a different scope.

If the command succeeds with a version change, proceed to step 4.

If the output indicates already up to date:

> Already running the latest version (v{version}).

Exit.

If the command fails, report the error and suggest:

> Update failed. You can try a manual reinstall:
>
> ```
> claude plugin uninstall --scope {scope} security-assessment@{marketplace}
> claude plugin install --scope {scope} security-assessment@{marketplace}
> ```

Exit.

### 4. Check companion dependency

If `dev-team@{marketplace}` is **not** installed, surface the dependency:

> WARNING: `dev-team@{marketplace}` is not installed but is required by
> `security-assessment` (primitives contract, codebase-recon agent,
> SARIF parser). Install it with:
>
> ```
> claude plugin install --scope {scope} dev-team@{marketplace}
> ```

This is informational — the security-assessment update has already
succeeded. The user can act on it after restart.

### 5. Confirm the update

```bash
claude plugin list
```

Report:

```
## Upgrade Complete

Previous: security-assessment v{old_version}
Updated:  security-assessment v{new_version}

Restart Claude Code to apply the update.
```

## Notes

- The `claude plugin update` command handles fetching, caching, and
  version management. Previous versions are kept for 7 days so active
  sessions continue working.
- A restart of Claude Code is required for the new version to take
  effect.
- Step 2 enables marketplace-level auto-update by writing
  `extraKnownMarketplaces.<marketplace>.autoUpdate: true` to
  `settings.json` — the same flag the `/plugin` UI toggles. With it on,
  routine releases for **both** plugins in the marketplace (`dev-team`
  and `security-assessment`) land without running `/upgrade` again.
