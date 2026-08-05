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

## Worker constraints

1. Write only the freeze-state file; do not edit source.
2. Do not enforce the lock yourself — the pre-tool-guard hook does.
3. **Be concise.** Confirm the locked scope in one line.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<glob-pattern>` (required) — glob pattern for files that ARE allowed to be edited (e.g., `src/auth/**`, `*.test.ts`)

If no pattern is provided, display usage and exit:
> Usage: `/freeze <glob-pattern>`
> Example: `/freeze src/auth/**` — only files under `src/auth/` can be edited.

## Steps

### 1. Write freeze state

Write the following JSON to `.claude/hooks/freeze-state.json` (relative to
the current repo root — **not** `hooks/freeze-state.json`, which would sit
inside the plugin's own shared install/cache directory and scope-lock every
other concurrently-running session, worktree, and project on the machine;
see issue #1890):

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

- The `hooks/pre_tool_guard.py` hook resolves this same path per invoking
  repo via `hooks/lib/artifact_paths.py`'s `resolve_file("hooks",
  "freeze-state.json")` — the same `.claude/`-scoped convention `.review-passed`
  and other per-repo runtime state already use — and blocks Write/Edit to
  files that do NOT match the allowed patterns.
- Freeze state persists across tool calls within a session, and is scoped to
  the repo it was activated in.
- If a session crashes while frozen, use `/unfreeze` in the next session to clear stale state.
- Multiple patterns can be provided as comma-separated: `/freeze src/auth/**,src/middleware/**`
- `/build` can also engage this same `.claude/hooks/freeze-state.json` contract automatically, per slice, when a plan opts into `**Scope enforcement:** freeze` and declares slice-level `**Files:**` (issue #865) — see `scripts/build_slice_scope.py` and the `build` skill's "Slice dispatch bookkeeping" section. That path is opt-in metadata, not a manual `/freeze` invocation, but writes/clears the identical file this command does.
