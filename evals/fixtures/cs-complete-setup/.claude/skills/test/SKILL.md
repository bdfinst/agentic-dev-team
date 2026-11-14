---
name: test
description: Run the unit tests and lint checks before a change is committed.
user-invocable: true
---

# Test

1. Run `npm test`. Report each failing test with its file and assertion.
2. Run `npm run lint`. Report each ESLint error and each file Prettier would reformat.
3. Report pass only when both commands exit 0.
