---
name: version-sync-check
description: Assert each plugin version equals its catalog entry version and ref
tools: Read, Grep, Glob
effort: medium
---

# Version Sync Check

Output JSON:

```json
{"status": "pass|fail", "issues": [{"file": "", "message": ""}], "summary": ""}
```

## Detect

For every `plugins/*/.claude-plugin/plugin.json`:

1. Read its `name` and `version`.
2. Find the matching entry in `.claude-plugin/marketplace.json` by `name`.
3. Assert `marketplace.json` entry `version` equals the plugin's `version`.
4. Assert `source.ref` equals `<name>-v<version>`.

Report one issue per mismatch with the exact expected and actual strings. The
output is fully determined by the two files — identical input always yields the
identical mismatch list, with no judgment involved.

## Ignore

Everything else.
