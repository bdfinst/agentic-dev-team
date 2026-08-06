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

## Worker constraints

1. Compose /careful + /freeze; introduce no new blocking behavior.
2. Do not edit source.
3. **Be concise.** Confirm both modes in one line each.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<glob-pattern>` (required) — glob pattern for files that ARE allowed to be edited

If no pattern is provided, display usage and exit:
> Usage: `/guard <glob-pattern>`
> Example: `/guard src/auth/**` — blocks destructive commands AND limits edits to `src/auth/`.
> Use `/careful off` and `/unfreeze` separately to disable, or pass `off` to disable both.

If argument is `off`:

1. Remove `.claude/hooks/careful-state.json` and `.claude/hooks/freeze-state.json`
2. Display: "Guard mode OFF. All safety restrictions lifted."

## Steps

### 1. Enable careful mode

Write to `.claude/hooks/careful-state.json` (repo-scoped — see the `/careful`
skill's Notes for why this is not `hooks/careful-state.json`; issue #1900):

```json
{
  "active": true,
  "enabled_at": "<ISO timestamp>"
}
```

### 2. Enable freeze mode

Write to `.claude/hooks/freeze-state.json` (repo-scoped — see the `/freeze`
skill's Notes for why this is not `hooks/freeze-state.json`; issue #1890):

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
>
> - Destructive commands: BLOCKED
> - File editing: Locked to `<pattern>`
>
> Use `/guard off` to disable both, or `/careful off` / `/unfreeze` individually.
