---
name: farley-score
description: Evaluate test quality using Dave Farley's 8 properties with a weighted Farley Score. Use when reviewing test suites, after writing tests, or when the user says "score my tests", "test quality", "Farley score", or "how good are my tests".
role: worker
user-invocable: true
---

# Farley Score

## Overview

Evaluates test quality using the 8 properties of good tests as described by Andrea Laforgia, based on Dave Farley's testing principles. Produces a quantitative "Farley Score" that teams can track over time.

Attribution: Andrea Laforgia / Dave Farley — properties of good automated tests.

**Locating the tests to score.** Prefer CodeGraph/Repowise over raw
`Grep`/`Glob` for finding the test files in scope and the production code
they exercise — grounding "Maintainable" and "Necessary" scores in real
coupling and call-graph data instead of guessing from test names alone. See
[`knowledge/codegraph-vs-graphify.md`](../../knowledge/codegraph-vs-graphify.md)
for tool selection and the fallback contract.

## The 8 Properties

Each property is scored 1-10:

| # | Property | Weight | Description |
|---|----------|--------|-------------|
| 1 | **Understandable** | 1.5 | Can a new team member read the test and understand what behavior is verified? Clear names, obvious arrange-act-assert structure, no hidden setup. |
| 2 | **Maintainable** | 1.5 | Can the test be updated without deep knowledge of the implementation? Minimal coupling to internals, no fragile selectors, uses abstractions (page objects, builders). |
| 3 | **Repeatable** | 1.2 | Does it produce the same result every time? No time-dependence, no external service calls, no shared mutable state, deterministic data. |
| 4 | **Atomic** | 1.0 | Does it test exactly one behavior? Single assertion concept (multiple asserts on one object are fine), no test interdependency, independent setup/teardown. |
| 5 | **Necessary** | 1.0 | Does it verify behavior that matters? Not testing framework code, not duplicating another test, covers a real scenario or edge case. |
| 6 | **Granular** | 1.0 | Does it fail with a clear, specific message? Pinpoints the failure location, doesn't require debugging to understand what broke. |
| 7 | **Fast** | 0.8 | Does it run quickly enough for the feedback loop? Unit tests <100ms, integration tests <5s, E2E tests <30s. |
| 8 | **First** | 1.0 | Was it written before or alongside the implementation (TDD)? Evidence: test commit predates implementation, test names describe behavior not implementation. |

### Scoring anchors — score from evidence, not intuition

Every property score must be justified by a specific line, assertion, or absence you can point to. **A score with no citation is a guess — re-read the test before assigning it.** Use these fixed anchors for every property:

| Band | Meaning | Example |
|------|---------|---------|
| 1-2 (Critical) | The property is actively violated | Repeatable scored 2: test calls `Date.now()` with no injected clock |
| 3-4 (Weak) | A real strength is present, but a violation still dominates | Maintainable scored 4: uses a builder for setup, but an assertion still reaches into a private internal field |
| 5-6 (Partial) | The property holds in general but has a specific counter-example in this test | Understandable scored 6: AAA structure is clear, but the assertion message is generic (`expect(result).toBeTruthy()`) |
| 7-8 (Solid) | An affirmative strength is cited, and a specific counter-example — a minor gap, not a violation — keeps it below Exemplary | Granular scored 8: asserts the specific error code, but no message text — a failure still needs the source to interpret why |
| 9-10 (Exemplary) | No counter-example found AND an affirmative strength cited | Atomic scored 10: exactly one behavior verified, no interdependency with other tests |

**9-10**: no counter-example found AND an affirmative strength cited. **Below 9**: a specific counter-example is required, UNLESS a strength justifies pulling a 1-2 score up into the 3-6 range.

**Property-specific rules that remove the most common ambiguity:**

- **First**: commit history is the primary evidence. When commit history is unavailable (e.g. reviewing a working tree with no VCS access), do not guess a number — fall back to the observable proxy: does the test name describe *behavior* (`should reject invalid email format`) or *mechanism* (`calls validateEmail with a regex`)? Behavior-named tests score 7-8 on this proxy alone (not 9-10 — the proxy is weaker evidence than commit history). If neither commit history nor a readable test name is available, mark the property `Unknown`, drop it from both the numerator and the weight total in the Farley Score formula, and state in the output that it was excluded — never substitute a default (e.g. 5) for missing evidence.
- **Necessary**: "duplicates another test" must name the specific other test by identifier. Never mark a test not-necessary from a hunch that "something else probably covers this."
- **Atomic**: multiple assertions on the *same* result object are one behavior, not a violation — do not penalize this pattern (see property description).

### Weighting

```
Farley Score = (sum of property_score × weight) / (sum of weights)
```

Total weight: 9.0 (or the reduced total when a property is scored `Unknown` per the First rule above — recompute both numerator and denominator without it). Maximum score: 10.0. This produces a 1-10 scale — never multiply by 10 or present it as a percentage.

### Score interpretation

| Range | Rating | Action |
|-------|--------|--------|
| 9.0 - 10.0 | Exemplary | Reference test — share as an example |
| 7.0 - 8.9 | Good | Minor improvements possible |
| 5.0 - 6.9 | Adequate | Specific improvements recommended |
| 3.0 - 4.9 | Poor | Significant rework needed |
| < 3.0 | Critical | Test provides false confidence — fix or delete |

### Suite-level score

Average the per-test scores. Report the distribution (how many Exemplary, Good, etc.).

## Output Format

```markdown
## Test Quality Report — Farley Score

**Suite**: `path/to/tests/`
**Tests scored**: 12
**Suite score**: 7.4 (Good)

### Distribution
- Exemplary (9+): 2
- Good (7-8.9): 6
- Adequate (5-6.9): 3
- Poor (3-4.9): 1

### Top Issues
1. **Maintainability** (avg 5.2): 4 tests coupled to implementation details — use behavior-based assertions
2. **Repeatability** (avg 6.0): 2 tests use `Date.now()` — inject time dependency
3. **First** (avg 6.5): Test names describe implementation ("calls handleSubmit") not behavior ("submits form data")

### Per-Test Scores (lowest first)
| Test | Score | Weakest Property | Suggestion |
|------|-------|-----------------|------------|
| `should call the API` | 4.2 | Understandable (2) | Rename to describe behavior, not mechanism |
| `test edge case` | 5.1 | Necessary (3) | Unclear what edge case — specify the condition |
```

Each row here summarizes one test; the per-property table backing it — every property scored with a citation — is computed the same way as the Worked Example below and must exist even when only this summary row is reported.

## Worked Example

Same test, scored the correct way and an ambiguous way that requires a correction. Use the correct version as the literal template; the incorrect version names the specific defects that made past outputs get redirected.

**Test under review:**

```js
test('should reject invalid email format', () => {
  const result = validateEmail('not-an-email');
  expect(result.isValid).toBe(false);
  expect(result.error).toBe('INVALID_FORMAT');
});
```

### Correct scoring output

```markdown
| Property | Score | Weight | Citation |
|----------|-------|--------|----------|
| Understandable | 9 | 1.5 | Name states the behavior; single arrange-act-assert block, no hidden setup |
| Maintainable | 8 | 1.5 | Asserts on the public `result` shape, not `validateEmail`'s internals, but the literal `'not-an-email'` input is inlined rather than named — a reader must infer why this string was chosen |
| Repeatable | 10 | 1.2 | Pure function call — no time, network, or shared state |
| Atomic | 9 | 1.0 | One behavior (rejecting a bad format); both assertions target the same result object |
| Necessary | 8 | 1.0 | Real edge case; no other test in the file asserts `INVALID_FORMAT`, but the test doesn't state why this specific malformed string was chosen over other invalid formats |
| Granular | 8 | 1.0 | Asserts the specific error code, but no message text — a failure still needs the source to interpret why |
| Fast | 10 | 0.8 | Unit test, no I/O |
| First | 7 | 1.0 | No commit history available; falling back to the name proxy — behavior-named, so 7-8 per the First rule, not 9-10 |

Farley Score = (9×1.5 + 8×1.5 + 10×1.2 + 9×1.0 + 8×1.0 + 8×1.0 + 10×0.8 + 7×1.0) / 9.0 = 77.5 / 9.0 = **8.6 (Good)**

| Test | Score | Weakest Property | Suggestion |
|------|-------|-------------------|------------|
| `should reject invalid email format` | 8.6 | First (7) | Confirm test predates implementation via commit history when available |
```

### Incorrect / ambiguous scoring output (avoid this)

```markdown
| Test | Score | Weakest Property | Suggestion |
|------|-------|-------------------|------------|
| `should reject invalid email format` | 7 | — | Looks fine overall |
```

This is exactly the shape that forces a correction, for three concrete reasons:

1. **No per-property breakdown.** For a test scored individually — not summarized in a suite's Per-Test Scores table — a single number with no property scores or citations cannot be audited or reproduced; there is no way to tell if `7` came from the weighted formula or was guessed.
2. **`Weakest Property` left blank.** The Output Format table requires naming the weakest property so the suggestion is actionable; `—` gives the reader nothing to act on.
3. **No arithmetic shown.** The correct output's total (77.5 / 9.0 = 8.6) is checkable by re-adding the eight weighted rows; `7` with no visible sum is unverifiable and, per the Scoring anchors rule above, a score with no citation is a guess.

## Integration

- **test-review agent**: Farley Score is computed at orchestrator level (`/test-design` for existing tests, `/build` Step 7 for branch tests) — not invoked directly from test-review.
- **QA Engineer agent**: Uses Farley Score in quality reports
- **Mutation testing skill**: Farley Score complements mutation score — high Farley + low mutation = assertions too weak
