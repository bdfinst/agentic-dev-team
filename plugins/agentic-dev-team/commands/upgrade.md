---
name: upgrade
description: >-
  Check for and apply plugin updates using the official Claude Code plugin
  update mechanism.
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash(claude *)
---

# Upgrade

Role: worker. This command updates the agentic-dev-team plugin to the latest version.

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

### 2. Run the update

```bash
claude plugin update agentic-dev-team@{marketplace}
```

Where `{marketplace}` is the marketplace name the plugin is installed from (e.g., `bfinster`).

If the command succeeds with a version change, proceed to step 3.

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

### 3. Confirm the update

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
