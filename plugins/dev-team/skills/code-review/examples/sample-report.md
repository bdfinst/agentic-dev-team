# Sample Code Review Report

```text
# Code Review Summary

| Agent              | Status | Issues |
|--------------------|--------|--------|
| test-review        | PASS   | 0      |
| structure-review   | FAIL   | 3      |
| naming-review      | PASS   | 0      |
| domain-review      | PASS   | 0      |
| security-review    | PASS   | 0      |
| js-fp-review       | WARN   | 3      |

Overall: FAIL (4 passed, 1 warned, 1 failed)
Total issues: 6 (1 error, 3 warnings, 2 suggestions)
```

## Issues by file

### src/api/handler.ts

- **ERROR** [structure-review] Line 15: Function `processRequest` nests 5 levels deep validating input before touching business logic
  - Fix: Extract validation, transformation, and persistence into separate functions

- **WARNING** [structure-review] Line 15: Function handles validation, business logic, and DB writes
  - Fix: Apply SRP — separate into validate(), transform(), persist()

- **WARNING** [js-fp-review] Line 42: `results.push(item)` — array mutation
  - Fix: Use `results = [...results, item]` or build with `.map()`

### src/utils/config.ts

- **WARNING** [js-fp-review] Line 8: `global.appConfig = merged` — global state mutation
  - Fix: Export a module-level getter instead

- **SUGGESTION** [structure-review] Line 1: File mixes config loading and validation
  - Fix: Split into config-loader.ts and config-validator.ts

- **SUGGESTION** [js-fp-review] Line 22: `let count` never reassigned
  - Fix: Use `const count`
