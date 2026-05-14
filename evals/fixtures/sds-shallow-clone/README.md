# Fixture: sds-shallow-clone

**Skill**: semantic-duplication-scan  
**Scenario**: Shallow clone blocks incremental mode

## Setup

1. A `computation-register.json` exists with a valid `lastScanCommit`
2. The git repository is a shallow clone (`git clone --depth 1 ...`)

## Expected Behavior

- Exit code: non-zero
- Output exact string: `Shallow clone detected — semantic-scan requires full history for incremental mode. Run with --full to override.`
- No modifications to the register

## Override

Running `/semantic-scan --full` on a shallow clone should skip this check and proceed with full-scan mode.
