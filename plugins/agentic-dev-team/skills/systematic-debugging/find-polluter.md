# Find Polluter

## When to Use

A test passes when run in isolation but fails when run as part of the full suite. Some earlier test is modifying shared state (global variable, database row, environment variable, singleton, file on disk) and not cleaning up.

## Algorithm: Binary Search Bisection

The goal is to find the single polluting test among potentially hundreds. Linear search is slow; binary search finds it in log2(N) steps.

### Steps

1. **Get the ordered test list.** Extract the full list of tests that run before the failing test, in execution order.
2. **Split the list in half.** Run the first half of the suite, then run the failing test immediately after.
   - If the failing test **still fails**: the polluter is in the first half.
   - If the failing test **passes**: the polluter is in the second half.
3. **Bisect the guilty half.** Take whichever half contains the polluter and split it again. Run that quarter, then the failing test.
4. **Repeat** until you have isolated a single test. That test is the polluter.
5. **Verify.** Run only the identified polluter followed by the failing test. Confirm the failure reproduces.

### Practical Notes

- Adapt to your test runner's filtering mechanism (`--filter`, `--run-only`, `--grep`, `-k`). The algorithm is the same regardless of language or framework.
- If your runner randomizes order, fix the seed or use the order from the failing run.
- Some runners have built-in bisect tools (e.g., RSpec bisect). Use them if available.

### After Finding the Polluter

Fix by: adding teardown/cleanup to the polluting test, isolating shared state (per-test transactions, fresh instances), or removing shared mutable state entirely.

Do not guess which test is the polluter. Bisect. With 256 tests, bisection takes 8 runs.
