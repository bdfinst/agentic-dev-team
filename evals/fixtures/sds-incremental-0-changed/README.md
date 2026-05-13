# Fixture: sds-incremental-0-changed

**Skill**: semantic-duplication-scan  
**Scenario**: Incremental scan with no changed files since lastScanCommit

## Setup

- Register exists with valid entries
- `git diff <lastScanCommit> HEAD --name-only` returns empty

## Expected Behavior

- No entries modified or re-annotated
- `lastScanCommit` updated to HEAD
- Output: `No changes since last scan — register up to date`
- Exit code: 0
