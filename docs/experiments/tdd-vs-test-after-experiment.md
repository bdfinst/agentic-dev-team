# Experiment: Test-First (TDD) vs. Test-After Workflow

**Status:** Proposed
**Owner:** dev-team maintainers
**Date:** 2026-06-21

## 1. Question

Does the existing test-first TDD workflow (`/build` with enforced
RED → GREEN → REFACTOR) produce better outcomes than a **test-after** workflow
(implement the whole feature, then write tests at the end) for small, testable
features?

"Better" is defined by four pre-committed success properties:

1. **Easy to change** — a follow-up change costs less and reworks less.
2. **Fully tested** — high coverage and few surviving mutants.
3. **Less agent rework** — fewer review-fix loops and test/CI re-runs.
4. **Lower token cost** — fewer total tokens / dollars to ship the feature.

## 2. Hypothesis

> **H1.** For small, testable features, the test-first arm ships at **equal or
> lower total token cost**, with **fewer rework cycles**, **higher mutation
> score at equal-or-higher coverage**, and a **cheaper follow-up change**, than
> the test-after arm.
>
> **H0 (null).** No material difference on the four properties (within trial
> variance).

We pre-register the decision rule in §7 **before** collecting data.

## 3. Design overview

A **paired, two-arm, repeated-trial** experiment. Each task is run through both
arms; arms are compared per-task to neutralize task-difficulty as a confound.
Because LLM output is stochastic, every (task × arm) cell is run for **N trials**
and we compare distributions, not single runs.

| | Arm A — Test-First | Arm B — Test-After |
|---|---|---|
| Plan | identical frozen plan | identical frozen plan |
| Implementation | `/build` with RED-GREEN-REFACTOR gates intact | implement all production code first, **no tests**, then add tests at the end to cover it |
| Reviews | identical review config | identical review config |
| Everything else | held constant | held constant |

### Two-stage protocol (this is what measures "easy to change")

Changeability cannot be read off a single implementation — it has to be
*exercised*. Each task therefore has two stages:

- **Stage 1 — Build.** Implement the base feature from a frozen spec.
- **Stage 2 — Change.** Apply a **withheld** change request (revealed only at
  Stage 2) on top of the Stage-1 output. The arm's own test suite is the safety
  net during the change.

Stage 2 cost and rework are the primary changeability signal: a well-tested,
well-factored Stage-1 result should make Stage 2 cheaper and safer.

## 4. Controlled variables (fairness rules)

The experiment is only credible if Arm B is a **good-faith** test-after workflow,
not a strawman. Hold these constant across both arms:

- **Same model** (one model id per campaign; report it).
- **Same frozen spec and same frozen plan** (planning happens once, shared).
- **Same review-agent configuration** and same auto-fix loop cap.
- **Same starting golden repo** (identical worktree seed).
- **Same definition of done (harness gate):** a stage **passes** only when all
  acceptance `testCommands` exit 0. This gate is **model-free** — code-review
  cleanliness, coverage, mutation, and Farley are **post-run sensors** (§6), not
  pass/fail gates.
- **Same coverage target (≥ 90% line + branch):** both arms' prompts instruct
  them to reach it; it is **measured and reported** per stage. This keeps the
  comparison "test-first vs test-after" rather than "tested vs untested," but a
  miss does not fail the harness gate — it is recorded as an outcome.
- **Execution order is immaterial.** Because every cell is fully isolated
  (§10 — own worktree + `$HOME`, fresh dispatch), there are no ordering effects
  to randomize away; cells may run in any order or in parallel.

Arm B definition (write it down so it is reproducible):
> Implement the complete feature to satisfy the spec with **zero** test files.
> Only after the implementation is complete, author a test suite targeting the
> same acceptance criteria and the same coverage target as Arm A.

## 5. Harness

A standalone experiment runner, `scripts/run_tdd_experiment.py`, **borrows the
worktree primitives** from the integration-eval tier (`extract_golden_repo`,
`init_worktree`, `run_commands`) but does **not** use the `integration` grader or
`eval_variance` — those are tuned for the plugin's own CI pyramid, not a
workflow A/B. The runner owns its own isolation, two-stage protocol, `--arm` /
`--trials` loops, and JSONL output.

- **Fixtures:** `evals/experiments/exp-tdd-<task>.json` (an `experiment` block) +
  `evals/fixtures/exp-tdd-<task>/` with `spec.md` (Stage 1), `change.md`
  (withheld Stage 2), `golden-repo.tar.gz`, `testCommands[]`,
  `changeTestCommands[]`. Kept out of `evals/expected/` so the unit grader and
  integration runner ignore them.
- **Pass/fail:** model-free — a stage passes when its declared commands exit 0.
- **Variance:** the runner records every trial; analysis aggregates per task per
  arm (§7, §11). It does not reuse `eval_variance.py`.

### Instrumentation gaps to close first

The cost/quality sensors are uneven — this must be addressed before the numbers
are defensible (repo "claims discipline"):

| Signal | Sensor today | Action |
|---|---|---|
| Total tokens / `cost_usd` | **Auto** — `hooks/cost-meter.sh` → `metrics/cost-metering.jsonl`, per **session** and per **thread** (main vs subagent) | **Run each (task × arm × trial) in its own session** so the session total *is* the per-arm cost. Per-phase attribution was removed (#170) and is not recoverable from the meter — do not depend on it. |
| Coverage (line+branch) | **Auto** — `/coverage-baseline`, `/coverage-delta` | Capture at end of each stage. |
| Mutation score / survivors | **Auto** — `/mutation-testing --emit-json` (`killed/total`, `survivors[]`) | Run on each stage's final suite. |
| Farley Score (incl. **First** = TDD evidence) | **Auto** — `/farley-score` | Sanity check that Arm A actually wrote tests first and Arm B did not — validates the manipulation. |
| `rework_cycles` | **No sensor** | Instrument as the **count of review-fix loop iterations** + **RED restarts** + **test-run invocations** before green, parsed from the run transcript. Log to the `performance-metrics` schema manually. |
| `hallucination_detected`, first-pass acceptance | **No sensor** | Log manually from transcript; treat as secondary/observational. |

## 6. Metrics → success properties

| Property | Primary metric | Secondary |
|---|---|---|
| Lower token cost | `tokens.total` & `cost_usd` per arm (Stage 1 + Stage 2) from cost-meter | tokens per passing test |
| Less rework | rework_cycles (loop iterations + restarts + failed test runs) | wall-clock, escalations to human |
| Fully tested | mutation score (1 − survived/total) | line+branch coverage, Farley Score |
| Easy to change | **Stage 2** cost + rework + Stage-2 mutation/coverage delta | complexity-review findings, Farley Maintainable/Understandable |

## 7. Pre-registered decision rule

Report **median across trials** per (task × arm) and the per-arm distribution.
Arm A ("TDD wins") is declared superior **only if** all four clauses hold,
aggregated across tasks (operators are explicit; the conjunction is **AND**):

- Stage-1 + Stage-2 **total tokens**: Arm A **≤** Arm B (no cost penalty), **and**
- **mutation score**: Arm A **≥** Arm B, at coverage Arm A **≥** Arm B, **and**
- **Stage-2 (change) total tokens** Arm A **<** Arm B **and** Stage-2
  **rework_cycles** Arm A **<** Arm B (both, not either), **and**
- overall **rework_cycles**: Arm A **≤** Arm B.

**Failure / censoring policy.** A cell whose Stage 1 never reaches green is
recorded as `passed:false`, its Stage 2 is **skipped**, and it is **excluded from
the cost/rework medians**; the per-arm **failure rate** is reported separately as
its own outcome. **Stopping rule:** fixed, pre-registered N — no early stop, no
peek-and-add.

If TDD is more expensive up front but materially cheaper/safer to change
(Stage 2), report that **trade-off explicitly** rather than forcing a single
winner — that is itself a publishable result and the most likely real outcome.

Pick the test by trial count: with small N report effect sizes + bootstrap CIs;
with larger N use a paired test (Wilcoxon signed-rank across tasks). State N and
the model id in the writeup.

## 8. Suggested corpus and scale

- **Tasks:** 5–8 small, fully-testable features/katas with a clean acceptance
  suite and an obvious follow-up change (String Calculator, a small parser, a
  pricing-rules function, a stateful cart, etc.). Keep them small so a feature is
  one session.
- **Trials:** set N from the §11 pilot (typically 5–10); report consistency.
- **Total runs:** see §11 for the worked scale (~8 tasks × 2 arms × ~6 trials ×
  2 stages ≈ 190 sessions). §8 and §11 must quote the same number.

## 9. Threats to validity

- **Stochasticity** → repeated trials + report variance/consistency, not single
  runs.
- **Strawman Arm B** → the fairness rules in §4 force Arm B to the same coverage
  target and same review gate; without this we would be measuring tested vs
  untested.
- **Manipulation check** → Farley "First" property + presence/absence of test
  files at Stage-1-impl-complete confirms each arm actually followed its protocol.
- **Task selection bias** → pre-register the corpus; report per-task results, not
  just the aggregate, so a single easy task can't swing the verdict.
- **Per-phase cost is unmeasurable** (#170) → design around session-total cost;
  do not claim phase-level attribution.
- **Grader gaming** → grading is deterministic and model-free (exit codes), so no
  judge bias; coverage/mutation targets are identical across arms.

## 10. Isolation — no cross-run context corruption

Three layers can leak; all three must be isolated. Worktree isolation alone is
not enough. The runner (`scripts/run_tdd_experiment.py`) enforces this per cell
(`task × arm × trial × stage`):

- **Filesystem** — each cell gets its own ephemeral git worktree (reused from the
  integration harness) **and** its own scratch `$HOME` / `CLAUDE_CONFIG_DIR` /
  `metrics/` / `memory/`. The cost-meter appends to
  `<root>/metrics/cost-metering.jsonl`; a private root means the session total
  *is* that cell's cost and parallel cells can't interleave-corrupt the JSONL.
- **Context window** — a cell is a **fresh `claude -p` dispatch**, never a session
  resume, so no reasoning carries across cells. **Stage 2 is dispatched as a new
  session seeded with the Stage-1 _files only_** — it sees the code but none of
  the build's reasoning, so changeability is measured, not memory.
- **Concurrency** — because every cell owns its worktree + `$HOME`, cells are safe
  to parallelize; within a cell, Stage 1 → Stage 2 run sequentially. For maximum
  independence, dispatch cells in separate containers.

**Contamination checks (verify isolation held).** Each row carries a
`contamination[]` field. A run is flagged/excluded if: a context **summarization**
fired (window filled → confound), or the private cost meter shows an unexpected
session count (state bled in). The Farley **First** property plus presence/absence
of test files at Stage-1-impl-complete is the **manipulation check** that each arm
actually followed its protocol.

## 11. Statistical validity — large enough, run enough

Two independent knobs:

- **Task size** (so the arms can diverge): ≥ 5–8 acceptance scenarios; a Stage-2
  change that **modifies** existing behavior (not just appends); small enough to
  finish in one context window (~1–3 dev-hours) so summarization never fires. Too
  small → no room for rework/changeability to differ; too big → summarization
  confound.
- **Trial count** (so model stochasticity is seen through): driven by a **pilot**,
  not a guess.
  1. **Pilot:** 1–2 tasks × ~10 trials/arm; measure the coefficient of variation
     (token cost is heavy-tailed) and the per-task paired effect size.
  2. **Power calc:** SE of a cell median ≈ sd/√n — halving the CI costs 4× trials;
     set N so the CI is well inside the pilot's effect (typically 5–10).
  3. **Unit of inference = the task.** Per task, take the median of N trials per
     arm, form the paired difference, then test **across tasks** (Wilcoxon
     signed-rank needs ≥ ~6 tasks; below that report effect sizes + bootstrap CIs,
     not a p-value). Trials estimate the cell; tasks give the verdict.
  4. **Pre-register** corpus, N, and stopping rule before collecting — no
     peek-and-add-trials until significant.

Defensible scale: **~8 tasks × 2 arms × 2 stages × ~6 trials ≈ 190 sessions**,
reported per-task (so one easy task can't swing the aggregate) plus the
across-task paired test.

## 12. Deliverables

1. **Scaffolded** — `scripts/run_tdd_experiment.py`: per-cell worktree + `$HOME`
   isolation, the two-stage protocol, `--arm`/`--trials` loops, best-effort
   rework parsing, and contamination checks. Self-tests with `--skip-dispatch`.
2. **Scaffolded** — experiment fixture layout under `evals/experiments/`
   (template + README + a minimal worked example exercising the plumbing).
3. **Next** — author the real sized-task corpus (golden repos + `spec.md` +
   withheld `change.md`) per §8/§11, run the pilot to set N, then the full
   campaign.
4. **Next** — wire the post-run sensors (`/coverage-*`, `/mutation-testing`,
   `/farley-score`) into each cell so §6's "fully tested" metrics land in the
   result row, and **verify the cost-meter output path** populates on a real
   dispatch before the campaign (the primary metric depends on it).
5. **Next** — a results report aggregating cost-meter, coverage, mutation, and
   rework **per task per arm** with the §7 decision rule applied.

> **Scope note.** This is an *experiment that uses the plugin*, not a permanent
> plugin feature. The runner and fixtures are throwaway measurement scaffolding;
> nothing here changes the shipped plugin's agents, skills, or hooks.
