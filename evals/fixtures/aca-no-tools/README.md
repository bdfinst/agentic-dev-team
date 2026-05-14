# Fixture: aca-no-tools

**Skill**: agent-create  
**Scenario**: Tools not provided — skill emits exact two-line prompt before proceeding

## Input

- name: `import-cycle-review`
- type: `review`
- description: `Detects circular import dependencies`
- tools: (not provided)

## Expected Behavior

Before any generation or file writing, the skill emits exactly:

```
Which tools does this agent need?
  Read, Grep, Glob (read-only) | add Edit, Write (file changes) | add Bash (shell) | add Skill (skill invocation) | add Agent (spawn subagents)
```

Line 1 is `Which tools does this agent need?` with no leading spaces.
Line 2 starts with exactly two spaces.

The skill does NOT proceed until the user responds to this prompt.

## Failure Conditions

- Any variation in prompt text → FAIL
- Skill proceeds to generation before prompt response → FAIL
- Prompt emitted more than once → FAIL
