# Mutation Testing: Time Estimation

Before running, estimate and present the expected duration to the user.

**Formula:** `mutation time ≈ (number of mutants) × (per-mutant test time)`

Tools optimize per-mutant time significantly:

- **Stryker** with `coverageAnalysis: "perTest"` runs only tests covering the mutated line, not the full suite. See [`languages/javascript-stryker.md`](languages/javascript-stryker.md).
- **pitest** with `withHistory` skips mutants killed in prior runs — first run is slow, incremental runs are fast. See [`languages/java-pitest.md`](languages/java-pitest.md).

**Rough heuristics (with per-test coverage analysis enabled):**

| Scope | LOC | Expected Duration |
| --- | --- | --- |
| Single small file | 50-200 | Seconds to ~1 min |
| Single medium file | 200-500 | 1-5 min |
| Multiple files / module | 500-1000 | 5-15 min |
| Full codebase | 1000+ | 10 min to hours |

The biggest variable is **test execution speed**, not mutant count. A project with slow integration tests will hurt far more than one with many mutants but fast unit tests.

**How to estimate for a specific project:**

1. Check how long the test suite takes: `time npm test` or `time mvn test`
2. Count approximate mutants: ~5-15 mutants per 100 LOC depending on code density
3. With per-test coverage: per-mutant time is typically 5-20% of full suite time
4. Without per-test coverage: per-mutant time ≈ full suite time (configure coverage analysis!)

**Present to user before running:**

> Mutation testing on `src/calculator.ts` (~150 LOC, ~20 mutants). Test suite runs in ~3s. Estimated time: under 1 minute. Proceed?

If the estimate exceeds 5 minutes, suggest scoping down or confirm the user is willing to wait.
