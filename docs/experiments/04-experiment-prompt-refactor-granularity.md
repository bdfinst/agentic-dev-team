# Experiment Prompt: Refactoring Granularity, the Test Safety Net, and Code/Test Authorship

**Type:** Reusable experiment prompt (hand this whole file to Claude to execute)
**Harness:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py) — **must be extended** (see "Extend the harness")
**Design + prior results:** [`02-final-results.md` § refactoring-cadence follow-up](02-final-results.md#proposed-follow-up-refactoring-cadence-and-the-test-safety-net)

This run resolves the open question from the *When Does TDD Pay Off?* study: the two
refactor workflows (`tdd-refactor` 664, `test-after-refactor` 678) were statistically
equivalent on changeability at n=3 — a 2% gap inside the noise. We cannot yet say whether
that gap is real, and if it is, what produces it. This experiment is powered to tell a
real **5%** difference from scatter, and it pulls apart the candidate mechanisms.

It judges every arm on three axes — **how modular and changeable the code is**, **how good
the tests are**, and **what that quality cost** — and reports quality both raw and
per-dollar, so the verdict names the efficient frontier rather than the most expensive arm.
The three axes and their sensors are defined in [What we measure](#what-we-measure--three-axes-define-these-before-running).

---

## Prompt

> Run a controlled experiment that varies **three things independently** and write a
> report. Use the existing harness `scripts/run_tdd_experiment.py` but **extend it** (do
> not rebuild it) to add the new arms, the two new sensors, and the split-authorship
> dispatch. Reuse the four `when-tdd-pays` tasks, both spec clarities, and the same
> 3-change chain. Work on a feature branch; commit the harness extension, fixtures, raw
> data, and the report; do not open a PR unless asked.
>
> **Factor 1 — refactor granularity (when the cleanup happens):**
> - **one-shot** — build the whole increment, then a single refactor pass at the end.
> - **continuous** — refactor on every increment / every green, in small steps.
>
> **Factor 2 — test protection during the refactor (are the tests allowed to move):**
> - **free** — the refactor step may rewrite, add, or delete tests (today's behavior).
> - **frozen** — the test files are read-only during the refactor; production code may be
>   restructured but the suite that existed at first-green must still pass unchanged.
>
> **Factor 3 — authorship (who writes code vs tests):**
> - **single-agent** — one agent writes both the production code and the tests.
> - **split-agent** — two independent agents: a *coder* writes only production code, a
>   separate *tester* writes only tests, neither sees the other's reasoning (only the
>   shared artifact contract — code and the spec).
>
> **Plus one external reference arm:** `tdd-refactor` (continuous, test-first,
> single-agent) — the anchor from the prior runs.
>
> **Run the full crossing:** 2 granularity × 2 protection × 2 authorship = **8 cells**,
> plus the `tdd-refactor` reference, across **4 tasks × {clear, vague} spec × N trials × 2
> stages** (build + 3-change chain). Pre-register N from a power calc (expect 12–15/cell).

---

## Pre-registered hypotheses (fix these before collecting any data)

Carried forward verbatim from the original draft, plus the authorship additions:

- **equivalence hypothesis (the default):** continuous-refactor and one-shot-refactor are
  equivalent on cumulative blast radius within a **±5%** margin (TOST). The n=3 data points
  here; this run is powered to *reject* it if a real effect exists.
- **granularity hypothesis:** holding test-protection constant, **continuous** refactoring
  yields lower blast radius than **one-shot**. Predicts the gap survives even when tests
  are frozen.
- **safety-net hypothesis:** **freezing** the suite during the refactor raises EDGE pass rate
  (the tests that recorded edge decisions survive) and lowers subsequent blast radius vs a
  free refactor. Predicts **test-suite churn mediates** the blast-radius difference.
- **authorship hypothesis:** **split-agent** raises EDGE pass rate and/or mutation score (an
  independent tester writes the behavior the coder didn't think to test) but may raise cost
  and the build-stage failure rate (two agents must converge on one contract). **Null:** a
  single agent testing its own code is as thorough as an independent tester — authorship
  does not move quality or changeability.
- **authorship-interaction hypothesis:** authorship interacts with protection — the value of an
  independent test author is largest when the refactor is **free** to churn the suite,
  because an independent suite is the thing a free refactor erodes (the test-after-refactor EDGE collapse).
  If frozen tests already neutralize churn, split-agent buys little on top.

granularity hypothesis, safety-net hypothesis, authorship hypothesis are not mutually exclusive; the 2×2×2 separates their contributions.

---

## Design — a 2×2×2, adequately powered

The granularity × protection face (Factor 1 × Factor 2), repeated at each authorship level:

| | tests **free** in refactor | tests **frozen** during refactor |
|---|---|---|
| **one-shot** (single pass after build) | test-after-refactor *(current arm)* | test-after-refactor-frozen |
| **continuous** (refactor each increment) | test-after-continuous | test-after-continuous-frozen |

Run that whole table once with **single-agent** authorship and once with **split-agent**,
plus `tdd-refactor` as the external reference. Reuse the same 4 tasks, vague **and** clear
spec, the 3-change chain.

**Power (do this first, with code).** The n=3 cells could not resolve a 2% effect.
1. Pull the per-cell cumulative-blast-radius values from the existing run1+run2 data under
   `docs/experiments/data/` and estimate the within-cell SD.
2. Size N for **80% power to detect a 5% difference** in blast radius (two-sided), and so
   that the ±5% TOST equivalence test is meaningful. Expect **N ≈ 12–15 per cell**.
3. **Pre-register the exact N and the stopping rule** in the report before running. The
   unit of inference is the **task**: per task take the median across trials, form the
   paired arm differences, test across tasks.

> **Scale check.** 8 cells × 4 tasks × 2 clarities × ~13 trials × 2 stages ≈ **1,600+
> dispatches** before the reference arm. If that is too costly, run it in **two phases and
> say so in the report**: Phase 1 settles the core question (the 2×2, single-agent only) and *gates*
> Phase 2 — only cross authorship (Factor 3) against the granularity/protection levels that
> Phase 1 showed actually move the metric. Pre-register the gate.

---

## What we measure — three axes (define these before running)

The whole point is to separate **how good the code/tests are** from **what that quality
cost**. Every cell reports all three axes per stage; the headline comparisons are
quality-at-fixed-cost and quality-per-dollar, never quality alone.

### Axis 1 — modularity & changeability of the code

- **Changeability (outcome, already in the harness):** cumulative **blast radius** — lines
  of production code touched to absorb the 3-change chain. Lower = more changeable. Also
  record the **per-change file fan-out** (distinct files touched per change) as a ripple
  measure: a modular design localizes a change to few files.
- **Modularity (structural, new offline sensor):** after the build stage, run the repo's
  read-only review agents against the agent's production code and **count findings**, the
  way [`complexity-refactor-regression.md`](../complexity-refactor-regression.md) established a
  baseline (mean findings/solution):
  - `complexity-review` — cyclomatic complexity, nesting depth, function size, parameter
    count.
  - `structure-review` — SRP violations, DRY, coupling, file organization.
  - `refactor-opportunity-review` — residual restructuring opportunities after green.
  Report each as findings/solution (lower = more modular) and as a combined modularity
  index. These are **offline graders run on the frozen build-stage files** — they never
  touch the worktree or the arm's own context.
- **Deterministic fallback (use if the agent graders are too slow or noisy at ~1,600
  cells):** the review agents are nested `claude -p` dispatches — non-deterministic and
  ~5–14 min each, which can dominate wall-clock and add run-to-run scatter to the very
  metric being measured. Run a **static, zero-model** modularity grader instead (or
  alongside, on a sample, to calibrate):
  - `radon cc -s` (cyclomatic complexity per function) and `radon mi` (maintainability
    index) — directly mirror `complexity-review`'s thresholds.
  - `lizard` — cyclomatic complexity, token count, parameter count, **and a built-in
    duplicate-code detector**, covering most of `structure-review`'s structural signal.
  Record the same shape (findings/solution, per-function complexity, an MI/duplication
  index) so the two graders are comparable. The static tools are deterministic, run in
  milliseconds, and add no token cost — preferred for the headline at this scale; reserve
  the agent graders for a **calibration subset** (e.g. one task × all arms) to confirm the
  static index tracks the agent findings, and report that correlation. `pip install radon
  lizard` in Preconditions if this path is taken.

### Axis 2 — quality of the tests

A suite is "good" only if it both **describes the right behavior** and **would catch a
regression**. Capture both, plus hygiene:

- **Behavioral correctness (already in the harness):** hidden-acceptance **CORE** pass rate
  (did the suite encode the stated behavior) and **EDGE** pass rate (did it encode the
  unstated edge decisions). EDGE is the suite's value as a safety net for later change.
- **Regression-catching strength (already in the harness):** **mutation score** (assertion
  strength — coverage can be high with empty assertions) and branch **self-coverage**.
- **Test hygiene (new offline sensor):** run `test-smell-review` (and optionally the
  `/farley-score` skill's 8-property score) on the frozen test files; record smell findings
  and, if used, the weighted Farley score. This catches the failure mode where a suite hits
  high coverage/mutation while being brittle or over-mocked. **Deterministic fallback** (same
  scale/noise concern as Axis 1): count the cheap, objective smells statically — assertion
  count per test, assertion-free tests, mock/patch density, sleep/time dependence, and test
  LOC — which capture most of the brittle/over-mocked signal at zero token cost. Reserve the
  agent grader for the calibration subset.

### Axis 3 — cost of attaining that quality

- **Direct cost (already in the harness):** `cost_usd` and tokens per stage, plus the
  **cumulative** build+change cost per task.
- **Cost-of-quality ratios (new, derived):** the metrics that actually answer the question —
  quality bought per dollar. Compute per cell:
  - **mutation score per $** and **branch-coverage point per $** (test-quality efficiency),
  - **EDGE pass rate per $** (safety-net efficiency),
  - **blast-radius reduction per $** vs the no-refactor baseline from the prior runs
    (changeability efficiency).
  Report the quality axes both **raw** and **per-dollar**, so a more thorough arm that costs
  more is judged on what the extra spend bought, not penalized or rewarded for spend alone.

> **Saturation guard.** On these small tasks coverage and mutation saturate (~100% / 1.0)
> for every arm — a known sensor ceiling. Treat any **uniform-across-arms** quality value as
> non-discriminating and lean on the axes that *do* separate here: blast radius, EDGE,
> modularity findings, and the cost ratios. Flag saturated metrics explicitly rather than
> reporting a meaningless tie.

---

## Extend the harness (do not rebuild it)

`run_tdd_experiment.py` today ships `ALL_ARMS = (test-first, test-after, build-pipeline,
batched-red)` and per-arm prompt strings in `ARM_PROMPTS` / `CHANGE_PROMPTS`. Add:

1. **New instruction arms** — `test-after-refactor`, `test-after-refactor-frozen`,
   `test-after-continuous`, `test-after-continuous-frozen` — as prompt strings that
   encode the granularity (one-shot vs per-increment refactor) and the protection rule.
   The **frozen** arms must instruct the agent: *the test files are locked during the
   refactor; restructure production code only, and every test that passed at first-green
   must still pass.* Enforce it mechanically too (see sensor 2 — a frozen cell with
   non-zero test churn is an arm violation, not a data point; flag and drop it).
2. **Split-authorship dispatch** — a flag (e.g. `--authorship split`) that runs the build
   stage as **two nested dispatches sharing one worktree**: a *coder* dispatch (writes
   production files, no test files) followed by a *tester* dispatch (writes test files
   only, given the code + spec, not the coder's transcript). The refactor step belongs to
   whichever arm owns it; under split-agent the refactor must respect the same test-file
   ownership boundary the protection factor sets. Default `--authorship single` keeps
   today's one-agent behavior.
3. **Two new sensors, recorded per stage** (these are the whole point):
   - **refactor granularity (actual):** count of distinct refactor edits between
     first-green and stage-complete — confirms the assigned arm behaved (continuous arms
     should show many, one-shot arms one). An arm whose actual granularity contradicts its
     label is a violation; flag it.
   - **test-suite churn during refactor:** **test LOC added + deleted** between first-green
     and post-refactor (diff the test files at those two checkpoints). **This is the
     mediator variable for safety-net hypothesis** — it is the number the user specifically wants tracked.
   - Carry forward the existing CORE/EDGE pass rates, blast radius, cost/stage, mutation,
     and contamination fields.
4. **Offline graders for the three axes** (post-stage, run on the frozen files — see "What
   we measure"). Default to the **deterministic static graders** at this scale: `radon` +
   `lizard` for the modularity index, a static smell counter for test hygiene — zero token
   cost, millisecond runtime, no run-to-run scatter. Optionally also wire the **agent
   graders** (`complexity-review`/`structure-review`/`refactor-opportunity-review` and
   `test-smell-review`) behind a flag, run only on a **calibration subset**, to confirm the
   static index tracks the agent findings. Either way the graders read the cell's files but
   never share its context. Emit the counts into the JSONL row alongside the live sensors;
   compute the **cost-of-quality ratios** (mutation/$, coverage-point/$, EDGE/$,
   blast-reduction/$) at analysis time from these fields — do not bake them into the row.
5. **Validate the extension with `--skip-dispatch`** (harness self-test, no model) before
   spending a cent — prove the new arms route, the split dispatch shares one worktree, and
   every sensor (the two new live sensors **and** the offline graders) emits on isolated
   cells.

Keep every cell isolated exactly as today: its own ephemeral worktree + scratch `$HOME`,
one JSONL row per cell-stage, flushed per cell.

---

## Fixed procedure (follow exactly)

### 0. Preconditions
- `pip install coverage pytest` (live sensors need them); add `pip install radon lizard` if
  using the deterministic modularity/test-hygiene graders (recommended at this scale — see
  Axis 1/2 fallbacks). Confirm the model id and that nested `claude -p` works (`IS_SANDBOX=1`
  is set by the harness for headless permissions).
- Reuse the four `when-tdd-pays` task fixtures and their **hidden** CORE/EDGE acceptance
  tests (kept out of the worktree; injected only at grading). Re-validate every acceptance
  file against a reference solution before running — never grade with broken tests.

### 1. Model
One **fixed, capable** model for the entire run; report it (e.g. `claude-sonnet-4-6`). Do
not mix models — the prior study showed the cost winner flips with model and size, so the
model is a controlled variable.

### 2. Power, then trials
Run the power calc (above) **first**, write the chosen N and stopping rule into the report,
*then* dispatch. Do not peek-and-extend N after seeing results.

### 3. Execute (sharded — cells are fully isolated)
Run one authorship level (and, if phasing, one phase) at a time. Launch parallel runners
writing separate JSONL files, then merge (dedupe by `task,arm,trial,stage,authorship`, keep
last). Shard the slowest tasks onto their own runners. **Monitor non-destructively** (poll
row counts / `pgrep`); never kill the session's own `claude` process.

### 4. Analyze (pre-registered — no post-hoc metric shopping)
- **Headline / question 1 (real vs noise):** **TOST** equivalence on cumulative blast
  radius, continuous vs one-shot, ±5% margin. A "confirmed equivalent" verdict is a valid,
  reportable result.
- **granularity hypothesis:** two-factor model on blast radius; granularity main effect with
  protection held constant.
- **safety-net hypothesis:** **mediation** — does test-suite churn account for the
  granularity/protection effect on blast radius? Plus the direct EDGE comparison frozen vs
  free (re-tests the test-after-refactor finding that a free refactor destroys edge coverage under a vague
  spec).
- **authorship hypothesis / authorship-interaction hypothesis (authorship):** authorship main effect on EDGE pass rate, mutation score,
  cost, and build-stage failure rate; authorship × protection interaction on EDGE and blast
  radius.
- **Modularity (Axis 1):** per-arm mean modularity findings/solution and per-change file
  fan-out; does continuous/frozen/split produce structurally cleaner code, and does lower
  modularity-findings predict lower blast radius across tasks?
- **Test quality (Axis 2):** per-arm CORE/EDGE, mutation, coverage, and test-smell counts —
  reported together so an arm cannot look good on coverage while failing EDGE or piling up
  smells.
- **Cost of quality (Axis 3):** the per-dollar ratios. Every quality comparison above is
  reported **twice** — raw, and divided by cumulative cost — and the recommendation names the
  efficient frontier (which arm gives the most changeability/test-quality per dollar), not
  just the highest-quality arm.
- **Sensor artifacts:** treat any **uniform-across-arms** quality value as a sensor ceiling
  and exclude it (coverage/mutation saturate on these tasks — flag, don't report as a tie);
  flag any non-empty `contamination`; drop (do not silently keep) frozen-arm cells whose
  test-churn sensor is non-zero.

### 5. Report
Write `docs/experiments/04-final-results.md`: the pre-registered N and power
calc, the 2×2×2 results grid, the TOST verdict, the two-factor models, the churn mediation,
the authorship effects, honest limitations (trials, model, single-task-family, sensor
caveats), reproducibility commands, and a recommendation. Commit the report **and** the raw
data under `docs/experiments/data/`. Mark the refactoring-cadence open question
from [`02-final-results.md`](02-final-results.md) resolved and link the new report.

---

## What each outcome would mean

| Result | Interpretation |
|---|---|
| **TOST confirms equivalence** | The refactor-arm tie is real; *refactoring is the mechanism* is the whole story, and **how** you refactor (granularity, ordering) does not move changeability. Choose between the two on cost and edge robustness. |
| **Granularity effect, no churn mediation** | Continuous refactoring is independently better. Recommend refactoring in small steps regardless of test ordering. |
| **Churn mediation (safety-net hypothesis)** | One-shot refactor's cost is collateral test-suite damage. Recommend protecting/regenerating the suite across a refactor; the test-after-refactor EDGE collapse and the changeability residual share one root cause. |
| **Authorship effect (authorship hypothesis)** | An independent test author finds behavior a self-testing agent misses. Recommend splitting code and test authorship — most valuable, per authorship-interaction hypothesis, when the refactor is free to churn the suite. |
| **Authorship null** | A single agent tests its own code as well as an independent one. Drop the split-agent overhead. |

A null on any factor is a publishable result: confirming the refactor workflows are
genuinely interchangeable on changeability — or that authorship does not matter — lets teams
choose on the axes that *did* separate cleanly (cost, edge robustness under vague specs).

---

## Guardrails (lessons already paid for — do not relearn)

1. **Hide acceptance tests during the build** (gradeFiles), or every arm just makes the
   given tests pass and the quality signal dies.
2. **Cost comes from the JSON result** (`--output-format json`), not the plugin cost-meter
   (it does not fire in nested dispatch).
3. **Hold the model fixed and report it** — the cost winner flips with model and size.
4. **Enforce "frozen," don't just ask for it.** The test-churn sensor is also the
   compliance check: a frozen cell with non-zero churn is an arm violation; flag and drop.
5. **Split-agent shares one worktree but not one context** — the tester gets the code +
   spec, never the coder's transcript, or the independence is fake.
6. **Pre-register N, the stopping rule, and the analysis** before any dispatch; the task is
   the unit of inference. No peeking-and-extending.
7. **Parallelize but isolate** — every cell already gets its own worktree + `$HOME`; safe
   to run many runners concurrently.

## Expected deliverables
- Harness extension: 4 new arms, `--authorship single|split`, the two new live sensors
  (refactor-granularity count, test-LOC churn), and the offline graders for the three axes
  (modularity findings, test-smell/Farley), all proven under `--skip-dispatch`.
- Raw data JSONL under `docs/experiments/data/`, carrying all three axes per cell.
- One report with the 2×2×2 grid; the TOST verdict; the churn mediation; the authorship
  effects; the three-axis tables (modularity & changeability, test quality, cost) with every
  quality figure shown raw **and** per-dollar; the named efficient frontier; and the refactoring-cadence
  status update in the summary.
