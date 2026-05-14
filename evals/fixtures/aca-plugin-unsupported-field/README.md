# Fixture: aca-plugin-unsupported-field

**Skill**: agent-create  
**Scenario**: User requests a plugin-unsupported field — exact warning emitted

## Input

- name: `db-reader`
- type: `review`
- description: `Validates database queries`
- hooks: `PreToolUse: [...validate query...]` (user explicitly requested this)

## Expected Behavior

Skill emits exactly:
```
hooks/mcpServers/permissionMode are silently ignored for plugin agents — move the file to .claude/agents/ if you need them to take effect
```

Then asks: `Include anyway? (yes/no)`

- On `no`: generated frontmatter omits `hooks`; skill continues normally
- On `yes`: generated frontmatter includes the `hooks` field as requested

## Note

The warning covers all three fields (hooks, mcpServers, permissionMode) even if only one was requested.

## Failure Conditions

- Warning text varies from the exact string above → FAIL
- Field included without asking → FAIL
- Field omitted without emitting warning → acceptable only if field was never requested
