# Fixture: sds-mode-incremental

**Skill**: semantic-duplication-scan  
**Scenario**: Register with valid lastScanCommit → incremental mode selected

## Expected Behavior

- Incremental mode: `git diff <lastScanCommit> HEAD --name-only` used for file selection
- Pre-flight shallow-clone check runs
- Only diff'd files are re-annotated
