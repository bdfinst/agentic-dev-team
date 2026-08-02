# Test-Cadence Tradeoffs: Evidence Bar for Displacing the Standing Cadence

`/build` runs exactly one cadence today — Code-First Small Batches — per
[ADR 0017](../../../docs/adr/0017-single-build-cadence-remove-classic-tdd-opt-in.md),
which removed the `--tdd` opt-in. Its stated reopening condition is scoped
to Classic TDD specifically ("a future, larger-corpus run of Experiment 5
... shows Classic TDD closing the cost gap"), but the principle behind it —
"that is a new decision to make with new evidence" — applies by the same
logic to any other cadence claim. This file is the operational note for
applying that bar to one such claim — batch-red-per-class (issue #1702) —
and for any future claim of the same shape.

## The standing default: Code-First Small Batches

**Code-First Small Batches** (IMPLEMENT → TEST → REFACTOR per behavior,
refactor on every green) is `/build`'s sole cadence (`plugins/dev-team/CLAUDE.md`
Core Principle 6, decided in ADR 0017). The decision rests on Experiment 5
(`docs/experiments/05-final-results.md`, n=24 cells/arm): $0.99/cell at
quality 0.961, versus Classic TDD's $1.59/cell at quality 0.966 —
statistically indistinguishable on maintainability, though Classic TDD
posts slightly lower mutation coverage — and Classic TDD is explicitly
endorsed by `docs/experiments/RECOMMENDATIONS.md` as a "sound second
choice." The big-batch and split-authorship shapes
tested in the same experiment line cost 2-4.5x more with worse
changeability (`docs/experiments/RECOMMENDATIONS.md` § 3) — a materially
larger gap than Classic TDD's ~60%, and not the comparison a new cadence
claim needs to clear.

## The external claim: batch-red-per-class

claude-flow's batch-vs-strict-TDD experiment (see the competitive analysis
in issue #1702) reports that batch-red-per-class testing (the source calls
it "batch-per-class") — write all tests for a unit, verify they fail as a
batch, then implement — is 46% cheaper and 61% more efficient (by test-run
count) than *plain strict row-by-row TDD*, with equivalent quality
(mutation-testing parity). That baseline is not this repo's Classic TDD
arm (`tdd-refactor`, which mandates a refactor after every green), and the
corpus and harness are claude-flow's, not this repo's.
Nothing in this repo's own experiment line measured
batch-red-per-class, so the claim doesn't yet compare to either of our two
validated cadences.

## The decision rule

**Do not adopt batch-red-per-class, and do not remove or deprecate
`skills/test-driven-development/SKILL.md`, on the strength of the external
claim alone.** This mirrors a working rule the repo already holds itself to
(root `CLAUDE.md` → "Deterministic tools over inference" /
"Verify a runtime property by exercising it at runtime"): an unreplicated
external report is a hypothesis, not a result, for a question this repo's
own experiment harness can answer directly.

| Question | Answer |
| --- | --- |
| Does an unreplicated external cadence claim, by itself, meet ADR 0017's reopening bar? | **No** — that bar is "a new decision to make with new evidence" from this repo's own harness, not a citation of someone else's. |
| Should `/build` switch its default cadence to batch-red-per-class? | **Not yet** — no local evidence exists. See `docs/experiments/test-cadence-validation-plan.md` for what a local run would require (monorepo-only — that path is dev-repo process and isn't present in an installed plugin). |
| Should strict TDD (`skills/test-driven-development`) be removed? | **Not yet** — same reason; it remains available advisory guidance per ADR 0017. |
| Should a `batch-red-verified` gate be added to `/build`? | **Not yet** — contingent on a local result, including "don't adopt it" as a valid outcome. Tracked as issue #1727. |

## Local measurement, once you have a result

Use `.claude/metrics/` (see `skills/performance-metrics/SKILL.md`) to keep
measuring cost/efficiency on real `/build` runs after adopting any cadence
change, the same way the plugin already tracks cost regressions elsewhere
(`skills/cost-report/SKILL.md`). A cadence change that looked good in a
local experiment must keep looking good in production use, or it gets
revisited — and, per ADR 0017, any change to the standing cadence is itself
a new ADR, not a knowledge-file edit.
