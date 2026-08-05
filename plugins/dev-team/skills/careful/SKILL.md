---
name: careful
description: >-
  Toggle careful mode. When active, destructive commands (rm -rf, force-push,
  DROP TABLE, etc.) are blocked instead of just warned about.
argument-hint: "[off]"
user-invocable: true
allowed-tools: Write, Read, Bash(rm *)
---

# Careful

Role: worker. This command toggles destructive command blocking.

You have been invoked with the `/careful` command.

## Worker constraints

1. Toggle state only; do not modify code or other config.
2. Do not block legitimate commands beyond the destructive set.
3. **Be concise.** Confirm the new mode in one line, no preamble.

## Parse Arguments

Arguments: $ARGUMENTS

- `off`: Disable careful mode
- No arguments: Enable careful mode

## Steps

### Enable (no arguments or any argument except "off")

1. Write the following JSON to `.claude/hooks/careful-state.json` (relative
   to the current repo root — **not** `hooks/careful-state.json`, which
   would sit inside the plugin's own shared install/cache directory and
   scope-lock every other concurrently-running session, worktree, and
   project on the machine; see issue #1900):

```json
{
  "active": true,
  "enabled_at": "<ISO timestamp>"
}
```

1. Display:

> Careful mode ON. Destructive commands will be blocked until `/careful off`.

### Disable (`off`)

1. Remove `.claude/hooks/careful-state.json`:

```bash
rm -f .claude/hooks/careful-state.json
```

1. Display:

> Careful mode OFF. Destructive commands will show warnings but not be blocked.

## Notes

- The `hooks/destructive_guard.py` hook resolves this same path per invoking
  repo via `hooks/lib/artifact_paths.py`'s `resolve_file("hooks",
  "careful-state.json")` — the same `.claude/`-scoped convention
  `freeze-state.json` and `.review-passed` already use. When active, matched
  commands exit with code 2 (block) instead of 0 (warn).
- Careful mode persists across tool calls within a session, and is scoped to
  the repo it was activated in.
- See `hooks/destructive-commands.json` for the full list of detected patterns and the safe allowlist.
