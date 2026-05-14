# Fixture: aca-invalid-name

**Skill**: agent-create  
**Scenario**: Invalid names are rejected with rule + correction; no file written

## Test Cases

### Case 1: Uppercase letters
- Input name: `CodeQuality`
- Expected error: `Name must match ^[a-z][a-z0-9-]*$ — use lowercase letters, digits, and hyphens only`
- Expected suggestion: `Did you mean: code-quality?`
- Expected: no file written, skill stops

### Case 2: Name starting with digit
- Input name: `3d-renderer-review`
- Expected error: `Name must match ^[a-z][a-z0-9-]*$ — use lowercase letters, digits, and hyphens only`
- Expected suggestion: a corrected form starting with a letter (e.g., `renderer-3d-review` or similar)
- Expected: no file written, skill stops

### Case 3: Name with spaces
- Input name: `my review agent`
- Expected error: same rule message
- Expected suggestion: `my-review-agent`
- Expected: no file written, skill stops

### Case 4: Empty string
- Input name: `""`
- Expected: same rule message, no correction offered
- Expected: no file written, skill stops

## Kebab-Case Correction Algorithm

Transform input to kebab-case suggestion:
1. Lowercase all characters
2. Replace runs of non-alphanumeric characters with a single hyphen
3. Strip leading/trailing hyphens
4. If result starts with a digit, prepend a hyphen then strip (or ask user)

Example: `CodeQuality` → `code-quality`
Example: `my Review Agent` → `my-review-agent`
Example: `3d-renderer` → digits at start, no clean correction → suggest user provide a valid name
