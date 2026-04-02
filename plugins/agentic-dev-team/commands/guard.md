---
name: guard
description: >-
  Activate both careful mode and freeze mode together. Blocks destructive
  commands and scope-locks editing to the specified pattern. Use for
  production-critical debugging sessions.
argument-hint: "<glob-pattern>"
user-invocable: true
allowed-tools: Write, Read
---

# Guard

Role: worker. Combined safety mode: careful + freeze.

You have been invoked with the `/guard` command.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<glob-pattern>` (required) — glob pattern for files that ARE allowed to be edited

If no pattern is provided, display usage and exit:
> Usage: `/guard <glob-pattern>`
> Example: `/guard src/auth/**` — blocks destructive commands AND limits edits to `src/auth/`.
> Use `/careful off` and `/unfreeze` separately to disable, or pass `off` to disable both.

If argument is `off`:
1. Remove `hooks/careful-state.json` and `hooks/freeze-state.json`
2. Display: "Guard mode OFF. All safety restrictions lifted."

## Steps

### 1. Enable careful mode

Write to `hooks/careful-state.json`:
```json
{
  "active": true,
  "enabled_at": "<ISO timestamp>"
}
```

### 2. Enable freeze mode

Write to `hooks/freeze-state.json`:
```json
{
  "active": true,
  "allowed_patterns": ["<glob-pattern>"],
  "frozen_at": "<ISO timestamp>"
}
```

### 3. Confirm

Display:
> Guard mode ON.
> - Destructive commands: BLOCKED
> - File editing: Locked to `<pattern>`
>
> Use `/guard off` to disable both, or `/careful off` / `/unfreeze` individually.
