# Fixture: sds-incremental-deleted-file

**Skill**: semantic-duplication-scan  
**Scenario**: Incremental scan removes entries for deleted files

## Setup

- Register has an entry for `src/pricing/calculator.js`
- `src/pricing/calculator.js` was deleted since `lastScanCommit`
- `git diff` returns `src/pricing/calculator.js` as a deleted file

## Expected Behavior

- Register entry for `src/pricing/calculator.js` is removed
- `lastScanCommit` updated to HEAD
- Exit code: 0
