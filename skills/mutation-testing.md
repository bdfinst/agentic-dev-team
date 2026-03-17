---
name: mutation-testing
description: Validate test suite quality by injecting mutants and checking whether tests detect them. Use after writing tests to verify assertions are meaningful, when evaluating test coverage quality, or as a CI quality gate on critical modules. High coverage with a low mutation score means weak assertions — your tests execute code without verifying behavior. Also use when someone asks "are my tests good enough?" or after TDD to verify the tests actually catch faults.
role: worker
user-invocable: true
---

# Mutation Testing

## Overview

Coverage tells you what code your tests execute. Mutation testing tells you if your tests would **detect changes** to that code. A test suite that achieves high code coverage but low mutation score has weak assertions — it runs the code without verifying meaningful behavior.

Mutation testing works by introducing small, deliberate changes (mutants) to production code and checking whether tests catch them. If a test fails, the mutant is "killed." If all tests pass despite the mutation, the mutant "survives" — revealing a gap in your test suite.

## Constraints
- Only run mutation testing after tests exist; do not use it as a substitute for writing tests
- Do not chase 100% mutation score; mark equivalent mutants as excluded
- Run targeted mutation on changed files for CI; reserve full-codebase runs for periodic audits
- Surviving mutants in critical paths require action; in trivial code they may be acceptable

## The 4-Step Process

### 1. Generate Mutants
Apply mutation operators to production code. Each operator category tests a different kind of assertion weakness:

| Operator Category | Example Mutation | What It Tests |
| --- | --- | --- |
| Arithmetic | `a + b` → `a - b`, `a * b` → `a / b` | Assertions on computed values |
| Conditional | `if (x)` → `if (true)`, `if (false)` | Branch coverage completeness |
| Equality | `===` → `!==`, `==` → `!=` | Equality check assertions |
| Relational | `x > 0` → `x >= 0`, `x < y` → `x <= y` | Boundary condition coverage |
| Logical | `a && b` → `a \|\| b`, `!a` → `a` | Boolean logic assertions |
| Unary | `-x` → `x`, `++x` → `--x` | Sign and increment assertions |
| Statement deletion | Remove a method call or assignment | Detection of missing behavior |
| Return value | `return x` → `return 0` / `return null` / `return true` | Assertions on return values |
| Null/boundary | `return obj` → `return null`, `""` → `"__mutated__"` | Null handling and edge cases |
| Array/method | `.filter()` → `.map()`, `.slice()` → `.splice()` | Method behavior assertions |
| Assignment | `x = y` → `x = 0`, `x += y` → `x -= y` | State mutation assertions |

### 2. Run Tests Against Each Mutant
Execute the test suite for each mutant. A mutant has one of four states:

| State | Meaning | Action |
| --- | --- | --- |
| **Killed** | At least one test fails | Good — your tests detect this change |
| **Survived** | All tests pass despite the mutation | Bad — triage and fix (see below) |
| **No coverage** | No test executes the mutated code | Write a test that reaches this code |
| **Equivalent** | Mutation produces identical behavior | Exclude from scoring (false positive) |

### 3. Calculate Mutation Score

```
mutation score = killed mutants / (total mutants - equivalent mutants) × 100
```

| Score | Interpretation |
| --- | --- |
| 90%+ | Strong test suite — assertions are thorough |
| 70-89% | Good but has gaps — review surviving mutants |
| 60-69% | Weak — significant assertion gaps exist |
| Below 60% | Tests provide false confidence — major rework needed |

### 4. Triage Surviving Mutants

When a mutant survives, follow this procedure:

1. **Equivalent mutant?** — Does the mutation produce identical behavior? If yes, mark as equivalent and exclude.
2. **Missing assertion?** — Does a test execute the mutated code but not assert on the affected output? If yes, strengthen the assertion.
3. **Missing test case?** — Is there no test that exercises the mutated path? If yes, write a new test.
4. **Undertested edge case?** — Does the mutation expose a boundary or corner case with no coverage? If yes, add an edge case test.

When strengthening tests, apply the same RED-GREEN discipline: write the test that fails against the mutant, then verify it passes against the original.

## Weak vs Strong Test Patterns

The most common mutation testing failure: tests that execute code without meaningfully asserting on behavior.

**Arithmetic operators** — Beware identity values that mask mutations:
```js
// WEAK: 0 is identity for addition — a + 0 === a - 0
expect(calculate(5, 0)).toBe(5);  // passes with + or -

// STRONG: use non-identity values that distinguish operators
expect(calculate(5, 3)).toBe(8);  // fails if + becomes -
```

**Conditional boundaries** — Test both sides:
```js
// WEAK: only tests the happy path
expect(isAdult(25)).toBe(true);

// STRONG: test the boundary itself
expect(isAdult(18)).toBe(true);   // exactly at boundary
expect(isAdult(17)).toBe(false);  // one below
```

**Return values** — Assert the actual return, not just truthiness:
```js
// WEAK: passes if return value changes from obj to true
expect(getUser(1)).toBeTruthy();

// STRONG: assert on the actual shape
expect(getUser(1)).toEqual({ id: 1, name: "Alice" });
```

**Statement deletion** — Verify side effects:
```js
// WEAK: doesn't detect if save() call is removed
processOrder(order);

// STRONG: verify the side effect occurred
processOrder(order);
expect(db.save).toHaveBeenCalledWith(order);
```

## Mutation Operator Selection by Context

Prioritize operators based on the code under test:

| Code Context | Priority Operators | Rationale |
| --- | --- | --- |
| Business logic | Relational, logical, return value, conditional | Decision correctness matters most |
| Data processing | Arithmetic, return value, null/boundary | Computation accuracy is critical |
| Control flow | Statement deletion, logical, relational, conditional | Path coverage gaps are high-risk |
| API boundaries | Return value, null/boundary, equality | Contract violations affect consumers |
| State management | Assignment, statement deletion, unary | State corruption is hard to debug |

## Integration with TDD

Mutation testing and TDD are complementary:

1. **TDD** ensures code is written to pass tests (tests drive design)
2. **Mutation testing** ensures tests would catch regressions (tests verify behavior)

After completing a TDD cycle, run mutation testing on the new code to verify your tests are strong enough. If mutants survive, strengthen assertions before moving on — this is cheaper than finding the gap later.

## Tool Integration (Optional)

For automated mutation testing, configure [Stryker](https://stryker-mutator.io/):

```json
// stryker.conf.json (JavaScript/TypeScript)
{
  "mutate": ["src/**/*.ts", "!src/**/*.test.ts"],
  "testRunner": "jest",
  "reporters": ["html", "clear-text", "progress"],
  "coverageAnalysis": "perTest"
}
```

Run with `npx stryker run`. For CI, use `--since <ref>` to limit to changed files.

## When to Apply

| Situation | Apply? |
| --- | --- |
| Validating test suite quality after TDD | Yes |
| Identifying weak assertions ("tests pass but I'm not confident") | Yes |
| After writing tests for legacy code | Yes |
| CI quality gate on critical modules | Yes |
| Reviewing a PR with test changes | Yes |
| No tests exist yet | No — write tests first |
| Prototype or spike code | No |
| Performance-critical hot loops (mutation overhead) | Targeted only |

## Guidelines

1. Mutation testing validates test quality, not code quality. Use it after tests exist, not instead of writing tests.
2. Start with targeted mutation on changed code. Full-codebase mutation is expensive and noisy.
3. Surviving mutants in critical paths require action. Surviving mutants in trivial code may be acceptable.
4. When a surviving mutant reveals a test gap, write a test that fails without the fix — same red-green discipline as TDD.
5. Equivalent mutants are noise. Mark and exclude them; do not chase 100% mutation score.
6. Avoid identity values in test inputs (0 for add/subtract, 1 for multiply/divide, empty string for concat) — they mask operator mutations.
7. Assert on specific values and shapes, not just truthiness — `toEqual(expected)` catches more mutants than `toBeTruthy()`.

## Output
Mutation score, list of surviving mutants with triage classification (equivalent/missing-assertion/missing-test/edge-case), and recommended test additions. Table format; skip killed mutants.

## Integration

- **[Test-Driven Development](test-driven-development.md)** — run mutation testing after TDD cycles to verify test strength
- **[Legacy Code](legacy-code.md)** — after writing characterization tests, use mutation testing to verify those tests catch behavioral changes
- **[Task Review & Correction](task-review-correction.md)** — surviving mutants in reviewed code indicate review gaps
- **[Accuracy Validation](accuracy-validation.md)** — mutation score as a quantitative confidence signal for test suite reliability
- **[Governance & Compliance](governance-compliance.md)** — mutation score thresholds as quality gates in compliance-sensitive modules
