---
name: unfreeze
description: >-
  Lift the scope lock set by /freeze. All files become editable again.
user-invocable: true
allowed-tools: Bash(rm *)
---

# Unfreeze

Role: worker. This command removes the file editing scope lock.

You have been invoked with the `/unfreeze` command.

Arguments: none — operates on the current freeze state.

## Worker constraints

1. Clear only the freeze-state file.
2. Do not edit source.
3. **Be concise.** Confirm the lock is lifted in one line.

## Steps

### 1. Remove freeze state

Delete `.claude/hooks/freeze-state.json` if it exists (the same per-repo
path `/freeze` writes and `hooks/pre_tool_guard.py` reads — see issue #1890):

```bash
rm -f .claude/hooks/freeze-state.json
```

### 2. Confirm

Display:
> Scope lock lifted. All files are editable.
