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

## Steps

### 1. Remove freeze state

Delete `hooks/freeze-state.json` if it exists:

```bash
rm -f hooks/freeze-state.json
```

### 2. Confirm

Display:
> Scope lock lifted. All files are editable.
