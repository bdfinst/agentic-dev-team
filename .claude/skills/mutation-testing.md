---
name: mutation-testing
description: Validate test suite quality by injecting mutants and checking whether tests detect them. Use after writing tests to verify assertions are meaningful, or as a CI quality gate on critical modules. High coverage with a low mutation score means weak assertions.
role: worker
user-invocable: true
---

# Mutation Testing

## Overview

Technique for evaluating test suite quality by introducing small changes (mutants) to production code and checking whether tests detect them. Mutation testing validates test effectiveness, not code correctness. A test suite that achieves high code coverage but low mutation score has weak assertions — it executes the code without verifying meaningful behavior.

## Constraints
- Only run mutation testing after tests exist; do not use it as a substitute for writing tests
- Do not chase 100% mutation score; mark equivalent mutants as excluded
- Run targeted mutation on changed files for CI; reserve full-codebase runs for periodic audits
- Surviving mutants in critical paths require action; in trivial code they may be acceptable

## Core Concepts

### Mutants and Mutation Operators

A mutant is a copy of the production code with one small, deliberate change. Mutation operators define the categories of changes applied:

| Operator Category | Example Mutation | What It Tests |
| --- | --- | --- |
| Arithmetic | `a + b` → `a - b` | Assertions on computed values |
| Relational | `x > 0` → `x >= 0` | Boundary condition coverage |
| Logical | `a && b` → `a \|\| b` | Boolean logic assertions |
| Statement deletion | Remove a method call or assignment | Detection of missing behavior |
| Return value | `return x` → `return 0` / `return null` | Assertions on return values |
| Null/boundary | `return obj` → `return null` | Null handling and edge cases |

### Mutation Score

```
mutation score = killed mutants / total mutants
```

A mutant is **killed** when at least one test fails due to the mutation. A mutant **survives** when all tests pass despite the mutation — indicating the test suite does not detect that behavioral change. Higher mutation scores indicate more thorough test suites.

### Equivalent Mutants

Mutations that produce semantically identical behavior to the original code. These are false survivors — they cannot be killed because no observable difference exists. Equivalent mutants must be identified and excluded from scoring to avoid inflating the denominator.

## Patterns

### Targeted Mutation Testing

Only mutate changed or critical code paths rather than the full codebase. Integrate with CI to run mutation analysis on files modified in a pull request. This keeps execution time practical and focuses feedback on the code under review.

### Mutation Operator Selection

Prioritize operators based on the code context:

| Code Context | Priority Operators | Rationale |
| --- | --- | --- |
| Business logic | Relational, logical, return value | Decision correctness matters most |
| Data processing | Arithmetic, return value, null/boundary | Computation accuracy is critical |
| Control flow | Statement deletion, logical, relational | Path coverage gaps are high-risk |
| API boundaries | Return value, null/boundary | Contract violations affect consumers |

### Surviving Mutant Triage

When a mutant survives, follow this procedure:

1. **Equivalent mutant?** — Does the mutation produce identical behavior? If yes, mark as equivalent and exclude.
2. **Missing assertion?** — Does a test execute the mutated code but not assert on the affected output? If yes, strengthen the assertion.
3. **Missing test case?** — Is there no test that exercises the mutated path? If yes, write a new test.
4. **Undertested edge case?** — Does the mutation expose a boundary or corner case with no coverage? If yes, add an edge case test.

### Incremental Mutation Testing

Run mutation analysis on changed files or lines only for regular CI feedback. Reserve full-codebase mutation runs as periodic audits (e.g., weekly or per release) to catch accumulated gaps without blocking daily development.

## When to Apply

| Situation | Apply? |
| --- | --- |
| Validating test suite quality | Yes |
| Identifying weak assertions | Yes |
| After writing tests for legacy code | Yes |
| CI quality gate on critical modules | Yes |
| No tests exist yet | No |
| Prototype or spike code | No |
| Performance-critical hot loops (mutation overhead) | No |

## Guidelines

1. Mutation testing validates test quality, not code quality. Use it after tests exist, not instead of writing tests.
2. Start with targeted mutation on changed code. Full-codebase mutation is expensive and noisy.
3. Surviving mutants in critical paths require action. Surviving mutants in trivial code may be acceptable.
4. When a surviving mutant reveals a test gap, write a test that fails without the fix — same red-green discipline as TDD.
5. Equivalent mutants are noise. Mark and exclude them; do not chase 100% mutation score.
6. Integrate mutation testing into CI as a quality gate on critical modules, not as a blocking gate on all code.
7. Combine with code coverage: high coverage + low mutation score means weak assertions.

## Output
Mutation score, list of surviving mutants with triage classification (equivalent/missing-assertion/missing-test/edge-case), and recommended test additions. Be concise — table format; skip killed mutants.

## Integration

- **[Legacy Code](legacy-code.md)** — after writing characterization tests, use mutation testing to verify those tests catch behavioral changes
- **[Task Review & Correction](task-review-correction.md)** — surviving mutants in reviewed code indicate review gaps
- **[Accuracy Validation](accuracy-validation.md)** — mutation score as a quantitative confidence signal for test suite reliability
- **[Governance & Compliance](governance-compliance.md)** — mutation score thresholds as quality gates in compliance-sensitive modules
