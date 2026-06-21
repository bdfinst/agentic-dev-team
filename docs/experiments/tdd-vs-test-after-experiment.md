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
- **Same definition of done:** Stage passes only when all acceptance test
  commands exit 0 **and** code review is clean. Arm B is *required* to reach the
  same coverage target at the end — otherwise we are comparing "tested" vs
  "untested," not "test-first" vs "test-after."
- **Randomize task order** per trial to avoid ordering effects.

Arm B definition (write it down so it is reproducible):
> Implement the complete feature to satisfy the spec with **zero** test files.
> Only after the implementation is complete, author a test suite targeting the
> same acceptance criteria and the same coverage target as Arm A.

## 5. Harness — reuse what already exists

This slots directly into the **integration-eval tier** (ADR 0007), which already
gives isolation, deterministic grading, and pass@k variance:

- **Fixtures:** add `evals/fixtures/exp-tdd-<task>/` integration fixtures, each
  with `spec.md` (Stage 1), `change.md` (withheld Stage 2), `golden-repo.tar.gz`,
  and `testCommands[]`. The existing `int-string-calculator` fixture is a model.
- **Isolation + grading:** `scripts/run_integration_eval.py` builds an ephemeral
  worktree, dispatches the workflow, runs `testCommands`, records exit codes, and
  tears down. The `integration` grader passes only when every command exits 0.
- **Variance:** run with `--trials N`; `scripts/eval_variance.py` records
  **pass@1, pass@k, consistency** to `metrics/eval-variance.jsonl`.
- **Two arms:** parameterize the run script with `--arm {test-first|test-after}`
  selecting the Arm-B prompt; or register a second grader genre. Either way it is
  one new module + one REGISTRY entry, no edits to existing graders.

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
Arm A ("TDD wins") is declared superior **only if**, aggregated across tasks:

- Stage-1 + Stage-2 **total tokens** are **≤** Arm B (no cost penalty), **and**
- **mutation score** is **≥** Arm B at **≥** Arm B coverage, **and**
- **Stage-2 (change) cost or rework** is **strictly lower**, **and**
- **rework_cycles** is **≤** Arm B.

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
- **Trials:** ≥ 5 per (task × arm) to see through model variance; report
  consistency from the variance harness.
- **Total runs:** 8 tasks × 2 arms × 5 trials × 2 stages ≈ 160 sessions — batch
  via the integration harness.

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

## 10. Deliverables

1. New integration fixtures under `evals/fixtures/exp-tdd-*/` (spec + withheld
   change + golden repo + test commands).
2. A `--arm` parameter (or second grader genre) on the integration run script,
   plus a small transcript parser that emits `rework_cycles` into the
   `performance-metrics` JSONL schema.
3. A results notebook/report aggregating cost-meter, coverage, mutation, and
   rework per arm with the §7 decision applied.
