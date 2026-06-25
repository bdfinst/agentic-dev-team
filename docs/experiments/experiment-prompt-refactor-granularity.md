# Experiment Prompt: Refactoring Granularity, the Test Safety Net, and Code/Test Authorship

**Type:** Reusable experiment prompt (hand this whole file to Claude to execute)
**Harness:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py) — **must be extended** (see "Extend the harness")
**Design + prior results:** [`when-tdd-pays-report.md` § RQ-F](when-tdd-pays-report.md#proposed-follow-up-rq-f-refactoring-granularity-and-the-test-safety-net),
[`when-tdd-pays-summary.md`](when-tdd-pays-summary.md)

This run resolves the open question from the *When Does TDD Pay Off?* study: the two
refactor workflows (`tdd-refactor` 664, `test-after-refactor` 678) were statistically
equivalent on changeability at n=3 — a 2% gap inside the noise. We cannot yet say whether
that gap is real, and if it is, what produces it. This experiment is powered to tell a
real **5%** difference from scatter, and it pulls apart the candidate mechanisms.

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

Carried forward verbatim from the RQ-F draft, plus the authorship additions:

- **H-F0 (equivalence, the default):** continuous-refactor and one-shot-refactor are
  equivalent on cumulative blast radius within a **±5%** margin (TOST). The n=3 data points
  here; this run is powered to *reject* it if a real effect exists.
- **H-F1 (granularity):** holding test-protection constant, **continuous** refactoring
  yields lower blast radius than **one-shot**. Predicts the gap survives even when tests
  are frozen.
- **H-F2 (safety net):** **freezing** the suite during the refactor raises EDGE pass rate
  (the tests that recorded edge decisions survive) and lowers subsequent blast radius vs a
  free refactor. Predicts **test-suite churn mediates** the blast-radius difference.
- **H-F3 (authorship):** **split-agent** raises EDGE pass rate and/or mutation score (an
  independent tester writes the behavior the coder didn't think to test) but may raise cost
  and the build-stage failure rate (two agents must converge on one contract). **Null:** a
  single agent testing its own code is as thorough as an independent tester — authorship
  does not move quality or changeability.
- **H-F4 (interaction):** authorship interacts with protection — the value of an
  independent test author is largest when the refactor is **free** to churn the suite,
  because an independent suite is the thing a free refactor erodes (the RQ-E EDGE collapse).
  If frozen tests already neutralize churn, split-agent buys little on top.

H-F1, H-F2, H-F3 are not mutually exclusive; the 2×2×2 separates their contributions.

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
> say so in the report**: Phase 1 settles RQ-F (the 2×2, single-agent only) and *gates*
> Phase 2 — only cross authorship (Factor 3) against the granularity/protection levels that
> Phase 1 showed actually move the metric. Pre-register the gate.

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
     mediator variable for H-F2** — it is the number the user specifically wants tracked.
   - Carry forward the existing CORE/EDGE pass rates, blast radius, cost/stage, mutation,
     and contamination fields.
4. **Validate the extension with `--skip-dispatch`** (harness self-test, no model) before
   spending a cent — prove the new arms route, the split dispatch shares one worktree, and
   both new sensors emit, on isolated cells.

Keep every cell isolated exactly as today: its own ephemeral worktree + scratch `$HOME`,
one JSONL row per cell-stage, flushed per cell.

---

## Fixed procedure (follow exactly)

### 0. Preconditions
- `pip install coverage pytest` (sensors need them); confirm the model id and that nested
  `claude -p` works (`IS_SANDBOX=1` is set by the harness for headless permissions).
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
- **H-F1 (granularity):** two-factor model on blast radius; granularity main effect with
  protection held constant.
- **H-F2 (safety net):** **mediation** — does test-suite churn account for the
  granularity/protection effect on blast radius? Plus the direct EDGE comparison frozen vs
  free (re-tests the RQ-E finding that a free refactor destroys edge coverage under a vague
  spec).
- **H-F3 / H-F4 (authorship):** authorship main effect on EDGE pass rate, mutation score,
  cost, and build-stage failure rate; authorship × protection interaction on EDGE and blast
  radius.
- **Sensor artifacts:** treat any **uniform-across-arms** quality value as a sensor bug and
  exclude it (the prior change-stage sensor had this); flag any non-empty `contamination`;
  drop (do not silently keep) frozen-arm cells whose test-churn sensor is non-zero.

### 5. Report
Write `docs/experiments/refactor-granularity-report.md`: the pre-registered N and power
calc, the 2×2×2 results grid, the TOST verdict, the two-factor models, the churn mediation,
the authorship effects, honest limitations (trials, model, single-task-family, sensor
caveats), reproducibility commands, and a recommendation. Commit the report **and** the raw
data under `docs/experiments/data/`. Update
[`when-tdd-pays-summary.md` § Open question](when-tdd-pays-summary.md) to mark RQ-F resolved
and link the new report.

---

## What each outcome would mean

| Result | Interpretation |
|---|---|
| **TOST confirms equivalence** | The refactor-arm tie is real; *refactoring is the mechanism* is the whole story, and **how** you refactor (granularity, ordering) does not move changeability. Choose between the two on cost and edge robustness. |
| **Granularity effect, no churn mediation** | Continuous refactoring is independently better. Recommend refactoring in small steps regardless of test ordering. |
| **Churn mediation (H-F2)** | One-shot refactor's cost is collateral test-suite damage. Recommend protecting/regenerating the suite across a refactor; the RQ-E EDGE collapse and the changeability residual share one root cause. |
| **Authorship effect (H-F3)** | An independent test author finds behavior a self-testing agent misses. Recommend splitting code and test authorship — most valuable, per H-F4, when the refactor is free to churn the suite. |
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
- Harness extension: 4 new arms, `--authorship single|split`, and the two new sensors
  (refactor-granularity count, test-LOC churn), proven under `--skip-dispatch`.
- Raw data JSONL under `docs/experiments/data/`.
- One report with the 2×2×2 grid, the TOST verdict, the churn mediation, the authorship
  effects, and the recommendation — plus the RQ-F status update in the summary.
