---
name: version
description: >-
  Report the installed version of the dev-team plugin.
user-invocable: true
allowed-tools: Bash
---

# Version

Role: worker. This command reports the installed plugin version. It is a purely
mechanical lookup — no reasoning, no file-by-file searching.

You have been invoked with the `/version` command.

Arguments: none.

## Steps

Run the resolver and report its output verbatim:

```bash
"$CLAUDE_PLUGIN_ROOT/hooks/lib/plugin_version.py"
```

The script reads `~/.claude/plugins/installed_plugins.json` (Claude Code's
install record) and resolves the version deterministically: a project-scoped
install for the current directory wins; otherwise it falls back to the
user-scoped install. It prints a single line, e.g.:

```
dev-team@bfinster v6.7.0 (scope: user)
```

- **Exit 0** — print the line as-is.
- **Exit 1** — the plugin is not recorded as installed; report exactly:
  `dev-team is not installed (no record in installed_plugins.json).`
- **Exit 2** — environment error (no `python3`, or the install record is
  missing); surface the script's stderr message verbatim.

Do not add commentary beyond the single result line.
