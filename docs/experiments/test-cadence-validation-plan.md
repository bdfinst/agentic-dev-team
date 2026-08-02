# Validating an alternative test cadence locally

Runbook for replicating an external test-cadence claim (e.g. claude-flow's
batch-red-per-class finding, see issue #1702) against this repo's own
Code-First Small Batches baseline, per
[ADR 0017](../adr/0017-single-build-cadence-remove-classic-tdd-opt-in.md)'s
reopening condition ("a new decision to make with new evidence"). See
[`../../plugins/dev-team/knowledge/test-cadence-tradeoffs.md`](../../plugins/dev-team/knowledge/test-cadence-tradeoffs.md)
for the decision rule this runbook exists to satisfy — that knowledge file
is what ships to consumers; this file is marketplace-repo development
process and does not ship.

## The harness

`scripts/run_refactor_experiment.py` runs isolated, worktree-scoped build
campaigns per arm/task/trial. Per its own docstring, it records: cost
(`cost_usd`/tokens/turns), test quality (CORE/EDGE/change pass, mutation
score, branch coverage, smells), changeability (blast radius), modularity
(radon/lizard), and process (refactor count, tests-frozen-during-refactor
violations). **It does not record test-run count** — the metric claude-flow's
"61% more efficient" figure is denominated in — **nor review-agent findings**.
Adding a batch-red-per-class arm to this harness does not, by itself, let
you compare on that specific axis; treat instrumenting test-run count as
part of the arm's setup cost, not a given.

No arm in this harness is currently configured as batch-red-per-class. The
closest existing analogue is `all-tests-first-single` ("All Tests, Then
Code (Single Agent)") — write all tests, then all code — which the base
campaign already measured at $2.31/cell, composite quality 0.525
(`05-final-results.md`'s "Efficiency frontier (quality per dollar)" table;
its mutation score alone is 0.978, in the separate "Raw metrics by arm"
table — mutation score is not the composite figure the standing default's
0.961 is quoted on) — worse composite quality at more
than double `continuous-single`'s $0.99/cell (`continuous-single` is the
harness's arm name for Code-First Small Batches, Single Agent). This
analogue is not evidence in batch-red-per-class's favor; it only bounds
the cost a similarly-shaped arm might run at. A dedicated
`batch-red-per-class` arm (tests-per-unit rather than tests-for-the-whole-task)
still needs to be added; `all-tests-first-single`'s numbers are a rough
reference point, not a substitute for running it.

## Steps

1. Add a `batch-red-per-class-single` arm to `run_refactor_experiment.py`
   (name it with the harness's `-single`/`-split` authorship suffix
   convention) alongside the existing `continuous-single` baseline arm —
   matching claude-flow's protocol (tests written and verified-red per
   unit, not for the whole task at once) as closely as the harness allows.
2. Run both arms against the same fixture tasks used in the base campaign
   (`evals/refactor-granularity/tasks/`: `cart`, `fare`, `grades`, `payroll`
   — the Experiment 04/05 corpus), at least 1 trial per task as a smoke
   test, more for a statistically meaningful result.
3. Compare cost and quality across arms — do not just compare against
   claude-flow's reported numbers; compare against this repo's own baseline
   run in the same session. If comparing on efficiency (test-run count) is
   important, instrument that first (see harness note above).
4. Write the result to `docs/experiments/`, following the existing report
   format, and update `docs/experiments/RECOMMENDATIONS.md` and
   [ADR 0017](../adr/0017-single-build-cadence-remove-classic-tdd-opt-in.md)
   if the result changes the standing recommendation.

## Cost note

Grounded in the base campaign's own per-cell costs
(`05-final-results.md`'s "Raw metrics by arm" table): `continuous-single`
at $0.99/cell and `all-tests-first-single` (the closest existing analogue)
at $2.31/cell. Two arms × 4 tasks × 1 trial ≈ $13; a more statistically
meaningful run (e.g. 3 trials/arm/task) scales roughly to $40. This is a
funded decision, not something to run as a side effect of another task.
Tracked as issue #1727; do not start it without explicit go-ahead.
