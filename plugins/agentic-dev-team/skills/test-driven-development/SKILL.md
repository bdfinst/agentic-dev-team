---
name: test-driven-development
description: Enforce RED-GREEN-REFACTOR cycle with hard gates. Use this skill whenever writing new code, fixing bugs, or adding features — any time implementation code will be written or modified. Prevents the common LLM failure mode of writing implementation first and tests later (or never). Also use when reviewing code to verify TDD discipline was followed.
role: worker
user-invocable: true
---

# Test-Driven Development

## Overview

Enforces strict RED-GREEN-REFACTOR discipline with verifiable gates. LLMs are especially prone to skipping tests or writing them after implementation — this skill exists because that tendency produces code that looks tested but isn't actually validated.

## Iron Law

**No production code without a failing test first.** If you didn't watch the test fail, you don't know if it tests the right thing. Code written before tests must be deleted and reimplemented from the test — no exceptions.

## Constraints
- Do not write implementation code without a failing test first
- Do not move to the next unit of work until all tests pass
- Do not skip the refactor step — it's where design quality happens
- Do not rationalize exceptions to the cycle (see Rationalization Prevention below)
- Use validated test doubles at architectural boundaries (external services, databases) — doubles are the preferred approach when backed by integration tests that verify them against real dependencies. Use real code for internal modules. See [contract testing pattern](../../knowledge/contract-testing.md).

## The Cycle

Each unit of work follows three phases with hard gates between them:

### 1. RED — Write a failing test
- Write the smallest test that describes the next behavior
- Use real code, not mocks, whenever avoidable
- Run the test suite — **the new test must fail**
- **Hard gate**: paste the failing test output. No output = no proceeding.
- Verify the failure is for the expected reason (missing feature, not a typo or import error)
- If the test passes without new code, the behavior already exists — pick a different test

### 2. GREEN — Make it pass
- Write the minimum implementation to make the failing test pass
- Run the test suite — **all tests must pass** with no errors or warnings
- **Hard gate**: paste the passing test output. No output = no proceeding.
- Do not add behavior beyond what the test requires
- Do not refactor yet

### 3. REFACTOR — Clean up
- Improve structure, naming, duplication — without changing behavior
- Run the test suite — **all tests must still pass**
- If tests break during refactor, undo and try a smaller change

Then return to RED for the next behavior.

## Rationalization Prevention

LLMs generate plausible excuses for skipping TDD. These are the common ones and why they're wrong:

| Excuse | Reality |
|--------|---------|
| "I'll add tests after the implementation" | You won't. And if you do, you'll write tests that pass by definition — they test what you wrote, not what should work. |
| "This is too simple to test" | Simple code breaks too. Testing takes 30 seconds. The one-line change that caused the most expensive bug looked simple too. |
| "Writing the test first would be slower" | TDD is faster than debugging. It catches errors at the cheapest possible moment. |
| "I need to see the implementation shape first" | That's called a spike. Do the spike, throw it away, then TDD the real implementation. |
| "The test framework isn't set up yet" | Set it up. That's the first task, not a reason to skip testing. |
| "I'm just refactoring, not adding behavior" | Then existing tests should pass throughout. If there are no existing tests, write characterization tests first. |
| "This is glue code / config / boilerplate" | Glue code that breaks takes down the system. If it can break, it needs a test. |
| "I already tested it manually" | Manual testing lacks systematic, re-runnable verification. It doesn't cover edge cases and you re-test every change. |
| "Deleting my existing code is wasteful" | Sunk cost fallacy. Unverified code is technical debt, not an asset. |
| "Let me keep my code as a reference and write tests first" | You'll adapt it instead of TDD-ing. That becomes testing-after with extra steps. |
| "The test is hard to write — I'll come back to it" | Hard-to-test code is hard-to-use code. The test is telling you the design needs work. Listen to it. |
| "TDD slows me down / I'm being pragmatic" | TDD is the pragmatic choice. Truly pragmatic means test-first because debugging costs more than testing. |

If you catch yourself composing an excuse not on this list, it's still an excuse. See also [anti-rationalization patterns](../../knowledge/anti-rationalization.md) for cross-cutting patterns beyond TDD. Write the test first.

## Red Flags Requiring Restart

Stop immediately and restart from RED if you notice:
- Writing implementation code before tests
- Adding tests after implementation
- Tests passing immediately without new implementation (testing existing behavior)
- Inability to explain why a test failed
- Tests deferred to "later"
- Any rationalization beginning with "just this once"
- Manual testing claims replacing automated verification
- "Keep as reference" or "adapt existing code" language
- Sunk cost justifications for keeping pre-test code

**Response**: Delete the code written without tests. Start over with RED.

## Verification Checklist

Before completing a unit of work:
- [ ] Every new function/method has a test
- [ ] Each test was watched failing before implementation
- [ ] Each failure occurred for the expected reason (missing feature, not typo)
- [ ] Minimal code written to pass each test
- [ ] All tests passing with clean output (no errors, no warnings)
- [ ] Tests use real code for internal modules; validated test doubles at architectural boundaries (see [contract testing](../../knowledge/contract-testing.md))
- [ ] Edge cases and error conditions covered

Missing any checkbox = TDD was skipped. Restart from RED.

## Exception Permissions

Ask your human partner before skipping TDD for:
- Throwaway prototypes (spike-and-discard)
- Generated code (scaffolding tools, codegen output)
- Configuration files with no behavioral logic

Even with permission, document the exception.

## Anti-Pattern: Horizontal Slicing

**DO NOT write all tests first, then all implementation.** This is "horizontal slicing" — treating RED as "write all tests" and GREEN as "write all code."

This produces bad tests:
- Tests written in bulk test *imagined* behavior, not *actual* behavior
- You end up testing the *shape* of things (data structures, signatures) rather than user-facing behavior
- Tests become insensitive to real changes — passing when behavior breaks, failing when behavior is fine
- You outrun your headlights, committing to test structure before understanding the implementation

**Correct approach: vertical slices via tracer bullets.** One test → one implementation → repeat. Each test responds to what you learned from the previous cycle.

```
WRONG (horizontal):
  RED:   test1, test2, test3, test4, test5
  GREEN: impl1, impl2, impl3, impl4, impl5

RIGHT (vertical / tracer bullet):
  RED→GREEN: test1→impl1
  RED→GREEN: test2→impl2
  RED→GREEN: test3→impl3
```

The first vertical slice is the **tracer bullet** — it proves the path works end-to-end before you invest in breadth. If the tracer bullet reveals a bad design assumption, you've wasted one cycle, not five.

## Integration with Phases

- **Phase 2 (Plan)**: Test strategy is part of the plan — identify what tests will be written for each unit
- **Phase 3 (Implement)**: Every unit of work follows RED-GREEN-REFACTOR. The inline review checkpoint runs after GREEN, not during RED.
- **Acceptance tests**: Feature file scenarios (Gherkin) define the outer loop. TDD operates within each scenario's implementation.

## Supporting References

- **[Testing Anti-Patterns](testing-anti-patterns.md)** — Load during RED phase when writing tests. Covers mock abuse, test-only methods, and other patterns that produce tests that pass but don't validate behavior.

## Output
Verified RED-GREEN-REFACTOR cycle evidence: failing test output, passing test output, and refactored code with passing tests for each unit of work.
