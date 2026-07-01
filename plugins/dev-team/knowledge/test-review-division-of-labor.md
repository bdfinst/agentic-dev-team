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

## test-smell-review ↔ test-design-advisor — remedy division

`test-smell-review` and `test-design-advisor` both draw remedy guidance from the
same knowledge set (`fixture-construction.md`, `result-verification.md`,
`test-organization.md`, `test-refactoring.md`). Rather than de-duplicate remedy
prose at report time, the two components divide the row structurally.
`test-smell-review` names the **smell + its remedy family** (the knowledge-file
cite); `test-design-advisor` names the **specific remedy pattern** and its
refactor sequence. `/test-design` joins the two on `remedyFamily` — no prose
matching, no silent drops.

| Column | Owner | Content |
|---|---|---|
| Smell name + location | test-smell-review | e.g. "Assertion Roulette at foo_test.js:42" |
| Severity + confidence | test-smell-review | `error` / `warning` / `suggestion`; `high` / `medium` / `none` |
| Remedy family (knowledge file) | test-smell-review | one of `fixture-construction`, `result-verification`, `test-organization`, `test-refactoring`, or `null` when no family applies |
| Specific remedy pattern | test-design-advisor | e.g. "Expected Object", "Custom Assertion", "Creation Method", "Delta Assertion" |
| Refactor sequence (behavior-preserving) | test-design-advisor | ordered steps from `test-refactoring.md` |
| Forward-design placement (pyramid, doubles) | test-design-advisor | table row from `test-pyramid.md` / `test-doubles.md` |

**Invocation rule.** When both components run together under `/test-design`,
the advisor owns the remedy-pattern columns and `test-smell-review` cites the
family only — the advisor's per-behavior recommendation is the specific fix.
When `test-smell-review` runs solo (e.g. under `/code-review`, where the
advisor is not dispatched), it fills the whole row: `suggestedFix` still names
a specific pattern from the family (not just the family slug), so no downstream
consumer is blocked on the advisor.

**Grader alignment.** The eval grader (`scripts/eval_graders/verdict.py:40`)
scans `issue.message` + `summary` prose for `mustMention` keywords. It does
not read `remedyFamily` structurally. So `test-smell-review` also emits the
family slug verbatim in the finding's `message` — this makes the family cite
enforceable by existing fixtures without extending the grader.
