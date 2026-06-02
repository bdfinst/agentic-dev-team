---
name: version
description: >-
  Report the installed version of the agentic-dev-team plugin.
user-invocable: true
allowed-tools: Read, Bash, Glob
---

# Version

Role: worker. This command reports the installed plugin version.

You have been invoked with the `/version` command.

## Steps

Find the installed plugin version by checking these locations in order:

1. **Project-level install**: Look for a `plugin.json` under the current project's `.claude/plugins/` directory that contains `"name": "agentic-dev-team"`. Use `find` or `Glob` to locate it.
2. **User-level cache**: List directories under `~/.claude/plugins/cache/bfinster/agentic-dev-team/` — each subdirectory name is a cached version. Report the highest version found.
3. **Marketplace source**: Read `~/.claude/plugins/marketplaces/bfinster/plugins/agentic-dev-team/.claude-plugin/plugin.json` and extract the `version` field.

Report the **first match found** (project > cache > marketplace).

Output format: `agentic-dev-team@bfinster v{version} (source: {project|cache|marketplace})`
