# Fixture: sds-fileline-accuracy

**Skill**: semantic-duplication-scan  
**Scenario**: file:line references point to the first line of each function definition

## Source File

`source.ts` — function `calculateTax` begins at line 7 (after 6 lines of comments/imports).

## Expected Behavior

- Register entry for `calculateTax` has `line: 7`
- Report output references `source.ts:7`
- If the file has not changed since annotation, no staleness note is appended
