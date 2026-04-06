---
name: version
description: >-
  Report the installed version of the agentic-dev-team plugin.
user-invocable: true
allowed-tools: Read
---

# Version

Role: worker. This command reports the installed plugin version.

You have been invoked with the `/version` command.

## Steps

1. Read `.claude-plugin/plugin.json`
2. Extract the `version` field
3. Output: `agentic-dev-team@bfinster v{version}`
