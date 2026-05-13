# Fixture: sds-mode-full-no-register

**Skill**: semantic-duplication-scan  
**Scenario**: No register exists → full-scan mode selected automatically

## Expected Behavior

- Full-scan mode: glob all source files in scope
- No pre-flight shallow-clone check (only runs in incremental mode)
- Proceeds to annotation of all source files found
