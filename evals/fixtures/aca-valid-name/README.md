# Fixture: aca-valid-name

**Skill**: agent-create  
**Scenario**: Valid name passes validation and skill proceeds

## Input

- name: `code-quality-review`
- type: `review`
- description: `Detects code quality violations including long functions and deep nesting`

## Expected Behavior

- Name `code-quality-review` matches `^[a-z][a-z0-9-]*$` — passes validation
- Skill proceeds to next step (tool selection or generation)
- No error message emitted about the name
- No file is written at this stage (fixture covers validation only)

## Edge Cases Covered

| Name | Expected |
|------|----------|
| `code-quality-review` | PASS — valid kebab-case |
| `a` | PASS — single lowercase letter |
| `my-agent-123` | PASS — letters, digits, hyphens |
