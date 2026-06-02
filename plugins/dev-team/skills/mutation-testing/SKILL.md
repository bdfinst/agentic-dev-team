---
name: mutation-testing
description: Validate test suite quality by running a real mutation testing tool and triaging surviving mutants. Use after writing tests to verify assertions catch behavioral changes, when evaluating test coverage quality, or as a CI quality gate on critical modules. The AI value here is triage — classifying survivors, writing fix tests — not generating or estimating mutations.
role: worker
user-invocable: true
---

# Mutation Testing

Wraps a real mutation tool (Stryker, pitest, mutmut, Stryker.NET) and adds AI triage of survivors. The tool generates mutations and reports survivors; the AI classifies survivors and writes fix tests. **Never estimate or guess mutation outcomes** — if no tool is available, help set one up; do not substitute reasoning for execution.

## Constraints

- **Always ask the user before running.** Present the time estimate and scope; get explicit approval. Mutation testing can be slow — never surprise the user.
- Only run after tests exist; mutation testing validates tests, it does not replace them.
- Do not chase 100% mutation score; equivalent mutants are noise.
- Scope to changed files by default; full-codebase runs are periodic audits.
- Surviving mutants in critical paths require action; in trivial code they may be acceptable.

## Time estimation

Use the heuristics in `references/tool-setup.md`. Present the estimate to the user; if > 5 minutes, suggest scoping down.

## Step 1: Detect or set up tooling

Detect and install the tool for the project's language (Stryker for JS/TS, pitest for Java/Kotlin, mutmut for Python, Stryker.NET for C#). Per-language detection and installation: `references/tool-setup.md`. **Do not proceed without a working tool.**

## Step 2: Run the tool (scoped to target)

Run scoped to user-specified files or changed files. Per-language commands: `references/tool-setup.md`. Capture full output and note HTML report paths.

## Step 3: Parse results

Extract surviving mutants. Map each to:

| Field | Source |
|---|---|
| File + line | Tool report |
| Mutation operator | Tool report (`ConditionalBoundary`, `NegateConditional`, etc.) |
| Original code | Read the source at that line |
| Mutated code | Tool report or infer from operator |
| Mutation score | Tool summary |

## Step 4: Triage survivors

For each survivor, classify and act:

| Classification | Meaning | Action |
|---|---|---|
| **Equivalent** | Mutation produces identical behavior | Mark excluded — no test can kill it |
| **Missing assertion** | Test executes the code but doesn't assert on affected output | Strengthen the assertion |
| **Missing test case** | No test exercises the mutated path | Write a new test |
| **Undertested boundary** | Mutation exposes a boundary/edge with no coverage | Add a boundary test |
| **Acceptable risk** | Trivial code where the mutation doesn't matter | Document and skip |

### Triage procedure

1. **Read the source context** — what does the code do and why.
2. **Check for equivalence** — does the mutation actually change observable behavior? Common equivalent patterns: dead code or unreachable branches; commutative-operation reorderings; conditions redundant with other guards; logging/debug-only code.
3. **Find related tests** — which tests cover this code; what do they assert.
4. **Classify** — missing assertion, missing test, boundary gap, or equivalent.
5. **Write the fix test** with RED-GREEN discipline: must fail against the mutant and pass against the original.

### Weak vs strong test patterns

Most survivors come from tests that execute code without meaningfully asserting on behavior:

**Arithmetic operators** — beware identity values (`0` for `+/-`, `1` for `*//`, `""` for concat):
```js
// WEAK: 0 is identity for addition — a + 0 === a - 0
expect(calculate(5, 0)).toBe(5);  // passes with + or -

// STRONG: non-identity values distinguish operators
expect(calculate(5, 3)).toBe(8);  // fails if + becomes -
```

**Conditional boundaries** — test both sides:
```js
expect(isAdult(18)).toBe(true);   // exactly at boundary
expect(isAdult(17)).toBe(false);  // one below
```

**Return values** — assert on the actual return, not truthiness:
```js
// WEAK: passes if return value changes from obj to true
expect(getUser(1)).toBeTruthy();
// STRONG: assert on shape
expect(getUser(1)).toEqual({ id: 1, name: "Alice" });
```

**Statement deletion** — verify side effects:
```js
processOrder(order);
expect(db.save).toHaveBeenCalledWith(order);  // catches removed save()
```

## Step 5: Fix and verify

1. **Verify the fix test fails against the mutant** — if possible, manually apply the mutation and run the test, or use the tool's re-run-specific-mutant feature.
2. **Re-run the mutation tool** on the same scope to confirm the mutant is killed.
3. **Report the updated mutation score.**

## Output format

```markdown
## Mutation Testing Results

**Tool:** Stryker 8.x | **Scope:** src/calculator.ts | **Duration:** 45s
**Score:** 82% (41 killed / 50 total, 3 equivalent, 6 survived)

### Surviving Mutants

| # | File:Line | Operator | Original | Mutated | Classification | Fix |
|---|---|---|---|---|---|---|
| 1 | calculator.ts:42 | ConditionalBoundary | `x > 0` | `x >= 0` | Missing boundary test | Add test: `expect(calc(0)).toBe(...)` |
| 2 | calculator.ts:67 | ReturnValue | `return result` | `return 0` | Missing assertion | Strengthen: assert on specific value |

### Equivalent Mutants (excluded)
| # | File:Line | Operator | Why equivalent |
|---|---|---|---|
| 1 | calculator.ts:15 | ArithmeticOperator | Dead code — branch unreachable |

### Recommended Test Additions
(Specific test code for each non-equivalent survivor)
```

## When not to apply

- No tests exist yet → write tests first.
- No tool installed and user declines setup → explain the limitation; do not estimate.
- Prototype or spike code.
