---
name: upgrade
description: >-
  Check for and apply plugin updates using the official Claude Code plugin
  update mechanism.
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
---

# Upgrade

Role: worker. This command updates the dev-team plugin to the latest version and ensures its marketplace is set to auto-update going forward.

Arguments: none.

You have been invoked with the `/upgrade` command.

## Worker constraints

1. Use the official plugin update mechanism; do not hand-edit installed plugin files.
2. Report available updates before applying.
3. **Be concise.** Report version deltas only.

## Steps

### 1. Read current version

Read the installed plugin's `plugin.json` to get the current version:

```bash
claude plugin list
```

Parse the output to find `dev-team` and its current version. Also read the installed `plugin.json` directly:

```
~/.claude/plugins/cache/*/dev-team/*/.claude-plugin/plugin.json
```

Report:
> **Current version**: dev-team v{version} (installed from {marketplace})

### 2. Check auto-update status and ask the user

First, report the current auto-update status (`enabled`, `disabled`, or `unknown`):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/upgrade/scripts/enable_autoupdate.py" --check
```

Then ask the user:

> Auto-update for the `{marketplace}` marketplace is currently **{enabled/disabled}**.
> Would you like to enable auto-update so future releases install automatically? (yes/no)

Wait for the user's answer before continuing. If they say **yes**, run the enable block below. If they say **no**, skip to step 3.

**Enable block** (run only if the user consents):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/upgrade/scripts/enable_autoupdate.py" --enable
```

This sets `extraKnownMarketplaces.<marketplace>.autoUpdate: true` (project settings first, else the config-dir user settings, seeding the entry from the marketplace registry when needed). It is idempotent — re-running reports "already enabled". Report the one-line result to the user, then continue to step 3.

> The same script backs the cloud bootstrap (`.claude/cloud-setup.sh`,
> `.claude/install-dev-team.sh`), which runs `--enable` non-interactively — one
> implementation of the flag, no duplication to keep in sync.

### 3. Run the update

First, determine the install scope from `claude plugin list` output (the `Scope:` line for `dev-team`). It will be one of: `user`, `project`, `local`, `managed`.

```bash
claude plugin update --scope {scope} dev-team@{marketplace}
```

Where `{scope}` is the detected install scope (e.g., `project`) and `{marketplace}` is the marketplace name (e.g., `bfinster`). The `--scope` flag is required — the CLI defaults to `user`, which will fail if the plugin is installed at a different scope.

If the command succeeds with a version change, proceed to step 4.

**Before concluding the update is broken or unnecessary, verify the catalog is current.** An "already up to date" result or a failed update is often a *stale marketplace catalog* pinned behind the latest release — not a broken update mechanism. Diff the marketplace's pinned version against the latest published release before drawing a conclusion:

- Compare the version in the marketplace source's `.claude-plugin/marketplace.json` (and the plugin's `.claude-plugin/plugin.json`) against the latest release tag/commit of the marketplace repo.
- If the catalog is behind the release, the root cause is the stale catalog, not `claude plugin update`. Refresh the marketplace (re-add it, or wait for its catalog to update) and re-run `/upgrade`.

If the output indicates already up to date:
> Already running the latest version (v{version}).

Exit.

If the command fails, report the error and suggest:
> Update failed. You can try a manual reinstall:
>
> ```
> claude plugin uninstall dev-team@{marketplace}
> claude plugin install dev-team@{marketplace}
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
- Step 2 checks the current auto-update status and asks the user before enabling it. The flag is `extraKnownMarketplaces.<marketplace>.autoUpdate: true` in `settings.json` (the same flag the `/plugin` UI toggles; there is no dedicated `claude plugin` CLI subcommand for it). With it on, routine releases land without running `/upgrade`.
