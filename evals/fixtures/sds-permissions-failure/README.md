# Fixture: sds-permissions-failure

**Skill**: semantic-duplication-scan  
**Scenario**: Register write fails due to file system permissions

## Setup

The project root directory is not writable by the current user (e.g., `chmod 555 .`).

## Expected Behavior

- Exit code: non-zero
- Output reports the exact path that could not be written AND the OS-level error
- Example: `Cannot write computation-register.json: EACCES: permission denied, open '/project/computation-register.json'`
- No partial register written
