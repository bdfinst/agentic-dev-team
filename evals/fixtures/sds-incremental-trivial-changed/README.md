# Fixture: sds-incremental-trivial-changed

**Skill**: semantic-duplication-scan  
**Scenario**: Incremental scan where all changed files are trivial after pre-filter

## Setup

- `computation-register.json` exists with entries from a prior scan
- 3 files have changed since `lastScanCommit`
- All 3 changed files contain only trivial functions after pre-filter

## Expected Behavior

- No entries added or modified in the register
- Output: `No new computation units found in changed files — register unchanged`
- Exit code: 0
- `lastScanCommit` is NOT updated (no successful annotation occurred)
