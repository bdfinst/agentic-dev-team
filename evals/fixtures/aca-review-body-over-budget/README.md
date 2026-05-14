# Fixture: aca-review-body-over-budget

**Skill**: agent-create  
**Scenario**: Review agent body exceeds 40 lines — trim diff shown before write gate

## Setup

A review agent spec that would naturally generate 45 lines of body
(e.g., many detection rules with verbose descriptions).

## Expected Behavior

1. Skill emits: `Body is 45 lines — 5 lines over the 40-line budget for review agents`
2. Skill lists each removed/collapsed item, each prefixed with `- ` (dash space)
3. Skill emits: `Approve this trim? (yes/no)`
4. **No file is written until user answers "yes"**

On `yes`: trimmed body is written
On `no`: skill emits `Options: (a) reduce spec scope and regenerate, (b) accept 45 lines and proceed without trimming`

## Failure Conditions

- File written before trim approval → FAIL
- Trim message text deviates from exact format → FAIL
- Items removed without being listed → FAIL
- Required sections (Output JSON, ## Skip, ## Detect, ## Ignore) removed during trim → FAIL
