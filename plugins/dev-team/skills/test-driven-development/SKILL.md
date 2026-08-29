---
name: test-driven-development
description: Advisory reference for the Classic RED-GREEN-REFACTOR TDD discipline with hard gates — not a build cadence toggle. The plugin's single build cadence is Code-First Small Batches (docs/experiments/RECOMMENDATIONS.md Rec 3); /build does not dispatch into this skill. Use on explicit user request when someone wants test-first discipline for the code being written, or when reviewing code to verify TDD discipline was followed by hand.
role: worker
user-invocable: true
---

# Test-Driven Development

## Overview

Enforces strict RED-GREEN-REFACTOR discipline with verifiable gates. LLMs are especially prone to skipping tests or writing them after implementation — this skill exists because that tendency produces code that looks tested but isn't actually validated.

**Positioning:** this is an **advisory methodology reference**, not a build cadence. `/build` runs a single cadence — Code-First Small Batches: implement one behavior, write its test in the same cycle, refactor on every green (`docs/experiments/RECOMMENDATIONS.md` Rec 3: test-first ordering by itself buys nothing; the per-green refactoring is the mechanism, and it is mandatory). `/build` never dispatches into this skill automatically. Use it only when a human explicitly asks for test-first discipline outside of `/build`, or when auditing existing code for TDD discipline after the fact. When applied, every rule below still holds — including the Iron Law and its hard gates.

**Defect fixes are not covered by this advisory status.** General feature development under `/build` uses Code-First Small Batches and never requires the full RED-GREEN-REFACTOR cycle in this skill. Fixing a bug is different and is **mandatory, not optional**: always reproduce the defect with a failing test before writing the fix. That hard gate lives in `skills/systematic-debugging/SKILL.md` Phase 4, not here — this skill remains advisory-only for new-feature construction.

## Iron Law

**No production code without a failing test first.** If you didn't watch the test fail, you don't know if it tests the right thing. Code written before tests must be deleted and reimplemented from the test — no exceptions.

## Constraints
- Do not write implementation code without a failing test first
- Do not move to the next unit of work until all tests pass
- Do not skip the refactor step — it's where design quality happens
- Do not rationalize exceptions to the cycle (see Rationalization Prevention below)
- Do not use mocks when real code is feasible — mocks test your assumptions, not your code

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

### 3. REFACTOR — Review then clean up

After GREEN, dispatch review agents **before** making any structural changes.

#### 3a. Post-GREEN review

1. **Always** — run `refactor-opportunity-review` on all changed files
2. **When non-trivial** (any changed function exceeds 20 lines, nesting exceeds 3 levels, or more than one function was modified) — also run `structure-review` on the changed files
3. Collect all `error` and `warning` findings from both agents — these are the refactor candidates for this cycle

#### 3b. Bounded fix loop (max 3 iterations)

Repeat until no `error`/`warning` findings remain, or 3 iterations have elapsed:

1. Apply the highest-severity finding — smallest behavior-preserving change possible
2. Run the test suite — **all tests must still pass**
3. If tests break: undo the change immediately; mark the finding as untouchable; move to the next finding
4. If tests pass: accept the change; move to the next finding

After 3 iterations, stop. Remaining findings are noted for the next cycle or escalated to the human.

#### 3c. Verify green

Run the full test suite one final time after the fix loop:

- **All tests must still pass** before leaving REFACTOR
- Do not proceed to the next RED cycle with any test red

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

If you catch yourself composing an excuse not on this list, it's still an excuse. Write the test first.

## Red Flags Requiring Restart

Stop immediately and restart from RED if you notice:
- Writing implementation code before tests
- Adding tests after implementation
- Tests passing immediately without new implementation (testing existing behavior)
- Tests deferred to "later"
- Any rationalization beginning with "just this once"
- Manual testing claims replacing automated verification
- "Keep as reference" or "adapt existing code" language
- Sunk cost justifications for keeping pre-test code

**Response**: Delete the code written without tests. Start over with RED.

**A failing test you can't explain is a debugging task, not a restart.** Do not delete code to escape an unexplained failure. Enter [Systematic Debugging](../systematic-debugging/SKILL.md) (reproduce → root cause); only once you understand *why* it failed do you decide whether the fix is code or a restart from RED.

## Verification Checklist

Before completing a unit of work:
- [ ] Every new function/method has a test
- [ ] Each test was watched failing before implementation
- [ ] Each failure occurred for the expected reason (missing feature, not typo)
- [ ] Minimal code written to pass each test
- [ ] The whole suite passing with clean output (no errors, no warnings) — a red test anywhere is failure, not just the ones this change touched; "pre-existing / not my diff" does not clear it
- [ ] Tests use real code (mocks only when unavoidable)
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

## Output
Verified RED-GREEN-REFACTOR cycle evidence: failing test output, passing test output, and refactored code with passing tests for each unit of work.
