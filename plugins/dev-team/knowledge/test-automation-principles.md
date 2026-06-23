# Test Automation Goals & Principles

Reference file for the `test-design-advisor`, `test-health`, and `cd-test-architecture` skills and the `test-smell-review` agent. This is the **value system** behind every other test knowledge file: the goals a test suite exists to serve and the principles that, when followed, keep it serving them. Use it as the **rubric** when *evaluating* a suite ("is this test good, and why/why not?") and as the **design constraints** when *recommending* a target architecture.

Source: Gerard Meszaros, *xUnit Test Patterns* (xunitpatterns.com) — Ch. 3 *Goals of Test Automation* and Ch. 5 *Principles of Test Automation*. Language- and framework-agnostic.

Core idea: every smell in `test-smells.md` is a **violated principle**, and every pattern in the other files is a **way to honor one**. A finding is more credible when it names the goal it protects and the principle it restores — not just "this is a smell."

---

## Goals — what the suite is *for*

A test is worth its maintenance cost only if it advances these. Grade each goal **served / weak / absent**.

| Goal | What it means | Lost when… |
|------|---------------|------------|
| **Tests as Specification** | The test states intended behavior before/while the code is written | Tests are written after the fact to match what the code already does |
| **Tests as Documentation** | A reader learns the SUT's behavior from the test alone | Obscure Test — intent buried in setup, helpers, magic values |
| **Defect Localization** | A failure points at *which* behavior broke, narrowly | Eager Test / shared fixtures — many tests fail together, none pinpoints |
| **Bug Repellent** | Tests catch regressions, so defects don't recur | Coverage gaps; tests that can't fail (see Buggy Tests) |
| **Fully Automated Test** | Runs with no human steps | Manual Intervention — someone seeds data or flips config |
| **Self-Checking Test** | The test decides pass/fail itself, no eyeballing output | Asserts missing; result printed but not verified |
| **Repeatable Test** | Same result every run, any order, anywhere | Erratic Test — clock/RNG/order/shared-resource dependence |
| **Robust Test** | Survives changes unrelated to the behavior it checks | Fragile Test — bound to internals, signatures, or call sequences |
| **Simple / Expressive Test** | Minimal, readable, one concern | Conditional logic, duplication, over-mocked interaction checks |

The first three are the *return* on the suite; the rest are the *conditions* that keep that return from leaking away. A suite that is green but **not Repeatable or not Robust** is a liability, not an asset — flag it as such.

---

## The Principles — how to honor the goals

The named principles, each with the test it should pass and the smell it prevents. When evaluating a test, walk this list; when designing one, treat it as a checklist.

| Principle | The rule | Honoring move | Violation smell |
|-----------|----------|---------------|-----------------|
| **Write the Test First** | Let the test drive the design; testability falls out for free | TDD red-green-refactor (`test-driven-development` skill) | Hard-to-Test Code retrofitted later |
| **Design for Testability** | The code must be reachable through a clean seam | Seams from `testability-patterns.md` | Hard-to-Test Code |
| **Use the Front Door First** | Exercise via the public API; verify via observable state | Round-trip test + State Verification | Overcoupled/Overspecified Software (Back Door overuse) |
| **Communicate Intent** | The test reads as a statement of behavior (≤ ~10 lines of logic) | Intent-revealing names, Test Utility Methods | Obscure Test |
| **Don't Modify the SUT** | Test the code you'll actually ship, in a representative config | Double *collaborators*, never the SUT itself | testing a stand-in instead of the SUT |
| **Keep Tests Independent** | Each test runs alone and in any order | Fresh Fixture per test; no shared writable state | Interacting Tests / Erratic Test |
| **Isolate the SUT** | Control every input by replacing what you don't test | Injection / lookup + the right double | Context Sensitivity (Fragile Test) |
| **Minimize Test Overlap** | Each condition covered by exactly one test | Test concerns separately; prune redundant tests | High Test Maintenance Cost |
| **Minimize Untestable Code** | Move logic out of hard-to-instantiate shells | Humble Object (`testability-patterns.md`) | Untested Code → Production Bugs |
| **Keep Test Logic Out of Production** | No `if (testing)` paths in shipped code | Seams, not back doors | Test Logic in Production |
| **Verify One Condition per Test** | One exercise, one logical assertion's worth of verification | Split tests; Custom Assertion to keep one call | Eager Test / Assertion Roulette |
| **Test Concerns Separately** | One behavior per test method/class | One Testcase Class per concern | Eager Test; poor Defect Localization |
| **Ensure Commensurate Effort** | Test effort/tooling ≤ feature effort/tooling | Data-Driven Test for config-shaped behavior | tests harder to write than the code |

---

## Using this as a rubric (evaluation)

For a given test or suite:

1. **Name the goals at risk.** Is it Repeatable? Robust? Does a failure localize? If any are *absent*, that is the headline finding — the suite is not yet trustworthy.
2. **Trace each finding to a principle.** "This is fragile" → *Isolate the SUT* / *Use the Front Door First* violated. The principle names the fix's direction.
3. **Reach for the pattern that restores it.** The remedy lives in `fixture-construction.md`, `result-verification.md`, `test-organization.md`, `test-doubles.md`, `value-patterns.md`, or `testability-patterns.md`.

A useful order of severity when grading: a suite that **can't fail** or **can't be trusted** (Buggy/Erratic) outranks one that is merely **hard to read or maintain** (Obscure/Fragile), which outranks **stylistic** issues.

---

## How this connects to the rest of the toolkit

- **`test-smells.md`** — each smell is the negative image of a principle here; that file is the detection layer, this is the *why*.
- **`test-refactoring.md`** — the behavior-preserving moves from a violated principle to an honored one.
- **`fixture-construction.md` / `result-verification.md` / `test-organization.md` / `value-patterns.md`** — the patterns that honor specific principles.
- **`testability-patterns.md`** — *Design for Testability*, *Minimize Untestable Code*, *Isolate the SUT* as production-code seams.
- **`cd-test-architecture.md` / `test-pyramid.md`** — *Keep Tests Independent* and *Repeatable Test* scaled up to pipeline determinism.
