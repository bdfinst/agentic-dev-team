# Fixture: sds-missing-commit

**Skill**: semantic-duplication-scan  
**Scenario**: lastScanCommit not in git history (e.g., after rebase)

## Setup

- `computation-register.json` has `lastScanCommit: "abc123def456"`
- That commit hash no longer exists in the git history

## Expected Behavior

- Output: `lastScanCommit not found in history — running full scan`
- Falls back to full-scan mode (does not exit non-zero)
- Proceeds to annotate all source files
