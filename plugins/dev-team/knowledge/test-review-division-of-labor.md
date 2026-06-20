# Test Review — Division of Labor

`test-review` and `test-smell-review` run over the same test files and can
detect several of the same signals under different names. This file is the
single source of truth for **how the two agents divide the work**, so the rule
lives in one place instead of being restated in both agents and in
`/test-design`.

## The two roles

- **`test-review`** owns the **tactical per-file gate**: an assertion is missing
  entirely, an `await` is missing, a mock is not reset, a coverage path (edge /
  error / happy) is untested, or production code is untestable (static factory,
  singleton, no injectable constructor → recommend the seam, never a test
  workaround).
- **`test-smell-review`** owns the **named design smell** and its remedy: it
  names the xUnit smell, judges test-double choice, and checks pyramid-layer
  placement, citing the remedy pattern (`fixture-construction.md`,
  `result-verification.md`, `test-organization.md`, `test-refactoring.md`).

## Shared signals — who reports when both run

Several signals are detectable by both agents. **When both run** (e.g. under
`/test-design`), the owner below reports it and the other agent stays silent on
it; the design-level framing wins. When an agent runs **solo**, it reports the
signal itself.

| Shared signal | Reported by (when both run) | Framing |
|---|---|---|
| Non-determinism (clock / RNG / sleep / real-I/O timing) | **test-smell-review** | the **Erratic Test** smell, with root cause |
| Weak / no-message assertions | **test-smell-review** | **Assertion Roulette** → `result-verification.md` |
| Copy-pasted arrange/assert blocks | **test-smell-review** | **Test Code Duplication** → builder / custom assertion |
| Magic literals in assertions | **test-smell-review** | **Hard-Coded / Magic Values** |
| Mocking concrete classes; wrong double choice | **test-smell-review** | test-double misuse |
| Unit test doing real I/O; wrong pyramid layer | **test-smell-review** | **Slow Tests** / pyramid placement |
| Missing assertion entirely; missing `await`; mock-reset hygiene | **test-review** | tactical mechanical gate |
| Testability blocker (static factory, singleton, no injectable ctor) | **test-review** | flag the blocker; recommend the production-code seam |

## The rule in one line

When both agents run, `test-smell-review` defers the pure mechanics (missing
assertion, missing `await`, mock-reset) to `test-review`, and `test-review`
defers the named-smell signals above to `test-smell-review`. `/test-design`
drops any duplicate that slips through, keeping the design-level framing.
