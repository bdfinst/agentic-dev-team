# Fixture: aca-validation-failure

**Skill**: agent-create  
**Scenario**: Generated agent fails /agent-audit — skill shows error, preserves inputs, offers recovery

## Setup

A generated agent file that is missing the `description` frontmatter field
(which agent-audit requires), simulating a validation failure.

## Expected Behavior

1. Skill runs `/agent-audit plugins/agentic-dev-team/agents/<name>.md`
2. `/agent-audit` returns errors (e.g., missing description)
3. Skill emits the raw `/agent-audit` output verbatim
4. Skill emits: `All your inputs are preserved.`
5. Skill emits: `(a) auto-correct and re-validate  (b) cancel`
6. **No file confirmed as written until user chooses (a) and re-validation passes**

On `(b)`: skill deletes the temporary file, makes no changes, stops.
On `(a)`: skill applies minimal corrections, re-runs /agent-audit, then:
  - Second pass succeeds → continue to write gate
  - Second pass fails → emit new /agent-audit output, emit "All your inputs are preserved.", emit the same menu again

## Failure Conditions

- Skill stops silently after second failure → FAIL
- Inputs lost after validation failure → FAIL
- Menu text deviates from `(a) auto-correct and re-validate  (b) cancel` → FAIL
