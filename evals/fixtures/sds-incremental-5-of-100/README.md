# Fixture: sds-incremental-5-of-100

**Skill**: semantic-duplication-scan  
**Scenario**: Incremental scan re-annotates only the files changed since lastScanCommit

## Setup

- Register has 100 entries across 100 source files
- 5 files have been modified since `lastScanCommit`
- 95 files are unchanged

## Expected Behavior

- Only 5 files are passed to the annotation LLM
- 95 entries in the register are preserved exactly (no re-annotation)
- `lastScanCommit` updated to HEAD
- Exit code: 0
- Progress output: `Annotating [1/5] <filename>` ... `Annotating [5/5] <filename>`
