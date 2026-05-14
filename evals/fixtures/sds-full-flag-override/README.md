# Fixture: sds-full-flag-override

**Skill**: semantic-duplication-scan  
**Scenario**: --full flag forces full re-scan even when register and history are intact

## Setup

- Register exists with valid `lastScanCommit`
- No source files have changed since that commit
- Command: `/semantic-scan --full`

## Expected Behavior

- Shallow-clone check is skipped
- All files in scope are re-annotated (not just diff'd files)
- `lastScanCommit` updated to HEAD
