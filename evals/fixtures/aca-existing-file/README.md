# Fixture: aca-existing-file

**Skill**: agent-create  
**Scenario**: Agent file already exists — skill reports it and asks for confirmation

## Setup

A file exists at `plugins/agentic-dev-team/agents/import-cycle-review.md` with:
```yaml
---
name: import-cycle-review
description: Old version — detects basic import cycles
---
```

## Input

- name: `import-cycle-review`
- type: `review`
- description: `New improved version for detecting circular import dependencies`

## Expected Behavior

Skill emits: `plugins/agentic-dev-team/agents/import-cycle-review.md already exists (description: Old version — detects basic import cycles)`

Then asks: `Overwrite? (yes/no)`

- On `no`: emits `Cancelled. Existing agent: plugins/agentic-dev-team/agents/import-cycle-review.md — Old version — detects basic import cycles` and stops. No file written or modified.
- On `yes`: skill continues to generation

## Failure Conditions

- File written without asking → FAIL
- Wrong file path or description in the message → FAIL
- Wrong question text → FAIL
- Skill continues after `no` → FAIL
