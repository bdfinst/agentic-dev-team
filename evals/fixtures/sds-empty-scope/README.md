# Fixture: sds-empty-scope

**Skill**: semantic-duplication-scan  
**Scenario**: First-time scan finds only trivial functions — no register created

## Setup

- No `computation-register.json` exists
- All source files in scope contain only trivial functions (getters, pass-throughs)

## Expected Behavior

- No `computation-register.json` is created
- Output: `No computation units found to analyze`
- Exit code: 0
