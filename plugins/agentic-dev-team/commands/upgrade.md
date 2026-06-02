---
name: upgrade
description: >-
  DEPRECATED stub: this plugin was renamed to dev-team@bfinster. /upgrade
  migrates the install in place.
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
---

# Upgrade — Legacy Plugin Stub

This plugin (`agentic-dev-team@bfinster`) has been renamed to
`dev-team@bfinster`. The new name has been live in the bfinster
marketplace since v6.0.0.

`/upgrade` in this stub does one thing: install the new plugin, then
uninstall this stub. After it runs, restart Claude Code; you'll be on
`dev-team@bfinster` (the real plugin) with all the agents, skills,
commands, and hooks intact under their new home.

## Steps

### 1. Detect install scope

Read `claude plugin list` and find the `Scope:` line for
`agentic-dev-team@bfinster`. It will be one of `user`, `project`,
`local`, `managed`.

```bash
claude plugin list
```

Capture the scope into `{scope}`. If detection fails, default to `user`.

### 2. Install the renamed plugin

```bash
claude plugin install --scope {scope} dev-team@bfinster
```

**Hard gate**: if this command exits non-zero, STOP. Report the failure
and the exact retry command:

> Migration failed: could not install dev-team@bfinster (network /
> marketplace / version conflict). The legacy plugin is still installed
> and functional. Retry with:
>
> ```
> claude plugin install --scope {scope} dev-team@bfinster
> ```

Do NOT proceed to step 3 — the user must keep the working stub until
the new plugin is in place.

### 3. Uninstall this stub

The install succeeded. Now remove the legacy stub:

```bash
claude plugin uninstall --scope {scope} agentic-dev-team@bfinster
```

If this fails, the new plugin is already installed — report the warning
and let the user clean up later:

> WARNING: dev-team@bfinster is now installed, but the legacy stub
> could not be uninstalled. You may have both plugins loaded. Remove
> the stub manually:
> claude plugin uninstall --scope {scope} agentic-dev-team@bfinster

### 4. Report and prompt for restart

```
## Migration Complete

  agentic-dev-team@bfinster (stub)  →  dev-team@bfinster

ACTION REQUIRED: restart Claude Code to load the renamed plugin.

After restart you'll have the full team (agents, skills, /code-review,
/plan, /build, /pr, …) under the new plugin id. Run /upgrade from
dev-team to enable auto-update.
```

## Why this stub exists

When the marketplace plugin id was renamed (`agentic-dev-team` →
`dev-team`), users running the pre-rename `/upgrade` were stranded:
the command called `claude plugin update agentic-dev-team@bfinster`,
which the marketplace catalog no longer served. This stub is
republished under the **old name** with the **same id but a higher
version**, so the old `/upgrade` resolves, fetches this code, and
hands control to the stub's `/upgrade` (above), which finishes the
migration.

Sunset: this stub is scheduled for removal from the marketplace catalog
no earlier than 2027-06-01 to give all installed users a chance to
migrate. See `docs/decisions/upgrade-step-0-sunset.md` (lives in the
real dev-team plugin) for the broader rename-cleanup timeline.
