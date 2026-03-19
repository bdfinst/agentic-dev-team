---
name: freeze
description: >-
  Scope-lock file editing to a specific glob pattern. Only files matching
  the pattern can be edited until /unfreeze is called.
argument-hint: "<glob-pattern>"
user-invocable: true
allowed-tools: Write, Read
---

# Freeze

Role: worker. This command restricts Write/Edit operations to files matching a glob pattern.

You have been invoked with the `/freeze` command.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<glob-pattern>` (required) — glob pattern for files that ARE allowed to be edited (e.g., `src/auth/**`, `*.test.ts`)

If no pattern is provided, display usage and exit:
> Usage: `/freeze <glob-pattern>`
> Example: `/freeze src/auth/**` — only files under `src/auth/` can be edited.

## Steps

### 1. Write freeze state

Write the following JSON to `hooks/freeze-state.json`:

```json
{
  "active": true,
  "allowed_patterns": ["<glob-pattern>"],
  "frozen_at": "<ISO timestamp>"
}
```

### 2. Confirm

Display:
> Scope locked to `<pattern>`. Only matching files can be edited.
> Use `/unfreeze` to lift the restriction.

## Notes

- The `pre-tool-guard.sh` hook reads `hooks/freeze-state.json` and blocks Write/Edit to files that do NOT match the allowed patterns.
- Freeze state persists across tool calls within a session.
- If a session crashes while frozen, use `/unfreeze` in the next session to clear stale state.
- Multiple patterns can be provided as comma-separated: `/freeze src/auth/**,src/middleware/**`
