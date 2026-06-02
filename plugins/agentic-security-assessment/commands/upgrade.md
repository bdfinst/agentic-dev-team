---
name: upgrade
description: >-
  DEPRECATED stub: this plugin was renamed to security-assessment@bfinster.
  /upgrade migrates the install in place.
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
---

# Upgrade — Legacy Plugin Stub

This plugin (`agentic-security-assessment@bfinster`) has been renamed
to `security-assessment@bfinster`. The new name has been live in the
bfinster marketplace since v3.0.0.

`/upgrade` in this stub does one thing: install the new plugin, then
uninstall this stub. After it runs, restart Claude Code; you'll be on
`security-assessment@bfinster` (the real plugin) with the full
SARIF-first pipeline, red-team harness, and all agents and skills
intact under their new home.

## Steps

### 1. Detect install scope

```bash
claude plugin list
```

Find the `Scope:` line for `agentic-security-assessment@bfinster` and
capture it into `{scope}`. Default to `user` if detection fails.

### 2. Install the renamed plugin

```bash
claude plugin install --scope {scope} security-assessment@bfinster
```

**Hard gate**: if this exits non-zero, STOP. Report:

> Migration failed: could not install security-assessment@bfinster. The
> legacy plugin is still installed and functional. Retry with:
>
> ```
> claude plugin install --scope {scope} security-assessment@bfinster
> ```

Do NOT proceed to step 3.

### 3. Uninstall this stub

```bash
claude plugin uninstall --scope {scope} agentic-security-assessment@bfinster
```

On failure:

> WARNING: security-assessment@bfinster is now installed, but the
> legacy stub could not be uninstalled. Remove manually:
> claude plugin uninstall --scope {scope} agentic-security-assessment@bfinster

### 4. Report and prompt for restart

```
## Migration Complete

  agentic-security-assessment@bfinster (stub)  →  security-assessment@bfinster

ACTION REQUIRED: restart Claude Code to load the renamed plugin.
```

If `dev-team@bfinster` is also installed but the user still has
`agentic-dev-team@bfinster`, suggest:

> The companion plugin agentic-dev-team has also been renamed. Run
> /upgrade from agentic-dev-team to migrate it.

## Why this stub exists

See `plugins/agentic-dev-team/commands/upgrade.md` § "Why this stub
exists" for the rationale. Same pattern: the old `/upgrade` called
`claude plugin update agentic-security-assessment@bfinster`, which the
catalog no longer serves under that name; this stub satisfies the
resolution and hands control to a migration command.

Sunset: scheduled for removal no earlier than 2027-06-01.
