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

## Parse Arguments

Arguments: $ARGUMENTS

- `off`: Disable careful mode
- No arguments: Enable careful mode

## Steps

### Enable (no arguments or any argument except "off")

1. Write the following JSON to `hooks/careful-state.json`:
```json
{
  "active": true,
  "enabled_at": "<ISO timestamp>"
}
```

2. Display:
> Careful mode ON. Destructive commands will be blocked until `/careful off`.

### Disable (`off`)

1. Remove `hooks/careful-state.json`:
```bash
rm -f hooks/careful-state.json
```

2. Display:
> Careful mode OFF. Destructive commands will show warnings but not be blocked.

## Notes

- The `destructive-guard.sh` hook reads `hooks/careful-state.json`. When active, matched commands exit with code 2 (block) instead of 0 (warn).
- Careful mode persists across tool calls within a session.
- See `hooks/destructive-commands.json` for the full list of detected patterns and the safe allowlist.
