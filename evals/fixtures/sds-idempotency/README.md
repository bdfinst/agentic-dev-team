# Fixture: sds-idempotency

**Skill**: semantic-duplication-scan  
**Scenario**: Running the scan twice with no code changes produces structurally identical output

## Setup

Any codebase with at least 3 non-trivial functions.

## Expected Behavior

- Run 1 produces `computation-register.json` with entries sorted by `file` then `function`
- No code changes made
- Run 2 produces a register where all entries have identical `file`, `function`, `layer`, `semanticDescription`, `promptVersion` fields
- `lastScanCommit` is excluded from the idempotency comparison (it changes between runs)
- Exit code: 0 both runs
