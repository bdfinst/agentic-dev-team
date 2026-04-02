---
name: mutation-testing
description: Validate test suite quality by running a real mutation testing tool and triaging surviving mutants. Use after writing tests to verify assertions catch behavioral changes, when evaluating test coverage quality, or as a CI quality gate on critical modules. The AI value here is triage — classifying survivors, writing fix tests — not generating or estimating mutations.
role: worker
user-invocable: true
---

# Mutation Testing

## Overview

Coverage tells you what code your tests execute. Mutation testing tells you if your tests would **detect changes** to that code. A test suite with high coverage but a low mutation score has weak assertions — it runs code without verifying behavior.

This skill wraps real mutation testing tools (Stryker, pitest) and adds AI-powered triage of surviving mutants. The tool does the deterministic work (mutate code, run tests, report survivors). The AI does the judgment work (classify survivors, explain gaps, write fix tests).

**This skill does NOT estimate or guess mutation outcomes.** If no mutation tool is available, it helps set one up. It does not substitute academic reasoning for actual test execution.

## Constraints
- **Always ask the user before running mutation testing.** Present the time estimate (see below) and scope, and get explicit approval. This applies during review workflows, build phases, and direct invocation. Mutation testing can be slow — never surprise the user with a long-running process.
- Only run after tests exist; mutation testing validates tests, it does not replace them
- Do not chase 100% mutation score; equivalent mutants are noise
- Scope to changed files by default; full-codebase runs are periodic audits
- Surviving mutants in critical paths require action; in trivial code they may be acceptable

## Time Estimation

Before running, estimate and present the expected duration to the user:

**Formula:** `mutation time ≈ (number of mutants) × (per-mutant test time)`

Tools optimize per-mutant time significantly:
- **Stryker** with `coverageAnalysis: "perTest"` runs only tests covering the mutated line, not the full suite
- **pitest** with `withHistory` skips mutants killed in prior runs — first run is slow, incremental runs are fast

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

## Step 1: Detect or Set Up Tooling

Check what's available in the project:

| Ecosystem | Tool | Detection |
| --- | --- | --- |
| JS/TS | [Stryker](https://stryker-mutator.io/) | `package.json` has `@stryker-mutator/core` or `stryker.conf.json` exists |
| Java/Kotlin | [pitest](https://pitest.org/) | `pom.xml` or `build.gradle` has `pitest` plugin |
| Python | [mutmut](https://mutmut.readthedocs.io/) | `mutmut` in requirements or pyproject |
| C#/.NET | [Stryker.NET](https://stryker-mutator.io/docs/stryker-net/introduction/) | `dotnet-stryker` in tool manifest |

**If no tool is found:** Help the user install one. For JS/TS projects:

```bash
npm install --save-dev @stryker-mutator/core @stryker-mutator/vitest-runner  # or jest-runner, karma-runner
npx stryker init
```

For Java with Maven:
```xml
<plugin>
  <groupId>org.pitest</groupId>
  <artifactId>pitest-maven</artifactId>
  <version>1.17.4</version>
</plugin>
```

**Do not proceed to mutation testing without a working tool.** If the user declines to install one, explain that this skill requires real test execution and cannot substitute estimation.

## Step 2: Run the Tool (Scoped to Target)

Run the mutation tool scoped to the files the user specified or to changed files:

**Stryker (JS/TS):**
```bash
# Specific files
npx stryker run --mutate "src/calculator.ts"

# Changed files only (CI mode)
npx stryker run --mutate "$(git diff --name-only HEAD~1 -- '*.ts' | grep -v test | tr '\n' ',')"
```

**Pitest (Java):**
```bash
# Specific class
mvn pitest:mutationCoverage -DtargetClasses="com.example.Calculator"

# With history (faster incremental runs)
mvn pitest:mutationCoverage -DwithHistory
```

**mutmut (Python):**
```bash
mutmut run --paths-to-mutate=src/calculator.py
```

Capture the full output. If the tool produces an HTML report, note its path for the user.

## Step 3: Parse Results

Extract surviving mutants from the tool output. Map each to:

| Field | Source |
| --- | --- |
| File + line | Tool report |
| Mutation operator | Tool report (e.g., "ConditionalBoundary", "NegateConditional") |
| Original code | Read the source at that line |
| Mutated code | Tool report or infer from operator |
| Mutation score | Tool summary |

## Step 4: Triage Survivors (AI Value)

This is where AI adds value the tool cannot. For each surviving mutant, classify it:

### Classification

| Classification | Meaning | Action |
| --- | --- | --- |
| **Equivalent** | Mutation produces identical behavior | Mark as excluded — no test can kill it |
| **Missing assertion** | A test executes this code but doesn't assert on the affected output | Strengthen the existing test's assertion |
| **Missing test case** | No test exercises the mutated path | Write a new test |
| **Undertested boundary** | Mutation exposes a boundary/edge case with no coverage | Add a boundary test |
| **Acceptable risk** | Trivial code where the mutation doesn't matter in practice | Document and skip |

### Triage Procedure

For each survivor:

1. **Read the source context** — understand what the code does and why
2. **Check for equivalence** — does the mutation actually change observable behavior? Common equivalent patterns:
   - Mutating dead code or unreachable branches
   - Changing order of commutative operations
   - Negating conditions that are redundant with other guards
   - Mutating logging/debug-only code
3. **Find related tests** — which tests cover this code? What do they assert?
4. **Classify** — missing assertion, missing test, boundary gap, or equivalent?
5. **Write the fix test** — using RED-GREEN discipline: the test must fail against the mutant and pass against the original

### Weak vs Strong Test Patterns

The most common reason mutants survive: tests execute code without meaningfully asserting on behavior.

**Arithmetic operators** — Beware identity values:
```js
// WEAK: 0 is identity for addition — a + 0 === a - 0
expect(calculate(5, 0)).toBe(5);  // passes with + or -

// STRONG: non-identity values distinguish operators
expect(calculate(5, 3)).toBe(8);  // fails if + becomes -
```

**Conditional boundaries** — Test both sides:
```js
// WEAK: only tests the happy path
expect(isAdult(25)).toBe(true);

// STRONG: test the boundary
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

## Step 5: Fix and Verify

After writing fix tests:

1. **Verify the fix test fails against the mutant** — if possible, manually apply the mutation and run the test to confirm it catches it. If the tool supports re-running specific mutants, use that.
2. **Re-run the mutation tool** on the same scope to confirm the mutant is now killed.
3. **Report the updated mutation score.**

## Output Format

```markdown
## Mutation Testing Results

**Tool:** Stryker 8.x | **Scope:** src/calculator.ts | **Duration:** 45s
**Score:** 82% (41 killed / 50 total, 3 equivalent, 6 survived)

### Surviving Mutants

| # | File:Line | Operator | Original | Mutated | Classification | Fix |
|---|-----------|----------|----------|---------|---------------|-----|
| 1 | calculator.ts:42 | ConditionalBoundary | `x > 0` | `x >= 0` | Missing boundary test | Add test: `expect(calc(0)).toBe(...)` |
| 2 | calculator.ts:67 | ReturnValue | `return result` | `return 0` | Missing assertion | Strengthen: assert on specific value |
| ... | | | | | | |

### Equivalent Mutants (excluded)
| # | File:Line | Operator | Why Equivalent |
|---|-----------|----------|---------------|
| 1 | calculator.ts:15 | ArithmeticOperator | Dead code — branch unreachable |

### Recommended Test Additions
(Specific test code for each non-equivalent survivor)
```

## When to Apply

| Situation | Apply? |
| --- | --- |
| Validating test suite quality after TDD | Yes |
| Identifying weak assertions ("tests pass but I'm not confident") | Yes |
| After writing tests for legacy code | Yes |
| CI quality gate on critical modules | Yes |
| Reviewing a PR with test changes | Yes |
| No tests exist yet | No — write tests first |
| No mutation tool installed and user declines setup | No — explain limitation, do not estimate |
| Prototype or spike code | No |

## Guidelines

1. **Always use a real mutation tool.** Do not estimate, guess, or academically reason about which mutants would survive. Run the tool, read the output.
2. Start with changed files. Full-codebase runs are expensive and noisy.
3. The AI's job is triage and fix-test authoring, not mutation generation. The tool handles generation deterministically.
4. When a surviving mutant reveals a test gap, write a test that fails against the mutant — same RED-GREEN discipline as TDD.
5. Equivalent mutants are noise. Classify and exclude them; do not chase 100%.
6. Avoid identity values in test inputs (0 for +/-, 1 for *///, empty string for concat) — they mask operator mutations.
7. Assert on specific values and shapes, not just truthiness.
8. If the mutation tool is slow, suggest configuration improvements (incremental analysis, history, per-test coverage analysis) rather than skipping the tool.

## Integration

- **[Test-Driven Development](test-driven-development.md)** — run mutation testing after TDD cycles to verify test strength
- **[Legacy Code](legacy-code.md)** — after writing characterization tests, use mutation testing to verify those tests catch behavioral changes
- **[Quality Gate Pipeline](quality-gate-pipeline.md)** — mutation score feeds Phase 1 confidence assessment; surviving mutants in reviewed code indicate review gaps
- **[Governance & Compliance](governance-compliance.md)** — mutation score thresholds as quality gates in compliance-sensitive modules
