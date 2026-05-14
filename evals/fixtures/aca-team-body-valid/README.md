# Fixture: aca-team-body-valid

**Skill**: agent-create  
**Scenario**: Team agent body generation produces valid, token-efficient output

## Input

- name: `schema-planner`
- type: `team`
- description: `Plans database schema migrations`
- tools: `Read, Grep, Glob, Edit, Write, Bash`
- model: `sonnet`

## Expected Body Properties

1. **Line count**: ≤ 75 lines
2. **Required section**: `## Responsibilities`
3. **Absent sections**: no Output JSON block, no `## Skip`, no `## Detect`, no `## Ignore`
4. **No "You are a/an" opener**
5. **No description restatement verbatim**
6. **No placeholder text**
7. **Each responsibility**: ≤ 2 lines, action-oriented

## Failure Conditions

- Body > 75 lines → FAIL
- Missing `## Responsibilities` → FAIL
- Contains Output JSON block → FAIL
- Contains `## Skip` → FAIL
- "You are a" opener → FAIL
