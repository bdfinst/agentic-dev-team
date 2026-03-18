---
name: test-design-reviewer
description: Evaluate test quality using Dave Farley's 8 properties with a weighted Farley Score. Use when reviewing test suites, after writing tests, or when the user says "score my tests", "test quality", "Farley score", or "how good are my tests".
role: worker
user-invocable: true
---

# Test Design Reviewer

## Overview

Evaluates test quality using the 8 properties of good tests as described by Andrea Laforgia, based on Dave Farley's testing principles. Produces a quantitative "Farley Score" that teams can track over time.

Attribution: Andrea Laforgia / Dave Farley — properties of good automated tests.

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

## Scoring

### Per-test score

```
Farley Score = (sum of property_score × weight) / (sum of weights)
```

Total weight: 9.0. Maximum score: 10.0.

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

## Integration

- **test-review agent**: Checks coverage and assertion quality; this skill adds quantitative scoring
- **QA Engineer agent**: Uses Farley Score in quality reports
- **Mutation testing skill**: Farley Score complements mutation score — high Farley + low mutation = assertions too weak
