# Consolidated Report: TDD vs. Test-After vs. the `/build` Pipeline

**Status:** Complete — three arms, six tasks, test-quality sensors
**Date:** 2026-06-21
**Design:** [`tdd-vs-test-after-experiment.md`](tdd-vs-test-after-experiment.md)
**Folds in:** [`tdd-vs-test-after-pilot-report.md`](tdd-vs-test-after-pilot-report.md),
[`tdd-vs-test-after-campaign-report.md`](tdd-vs-test-after-campaign-report.md)
**Raw data:** [`data/tdd-campaign-2026-06-21.jsonl`](data/tdd-campaign-2026-06-21.jsonl)
(72 rows, instruction arms) · [`data/tdd-buildpipeline-2026-06-21.jsonl`](data/tdd-buildpipeline-2026-06-21.jsonl)
(24 rows, `/build` arm)
**Runner:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py)

## Executive summary

Three workflows were compared on six small, fully-tested features, each with a
withheld follow-up change, every cell isolated and graded by hidden acceptance
tests on `claude-haiku-4-5`:

1. **test-first** — strict RED-GREEN-REFACTOR (prompt-level).
2. **test-after** — all code first, tests at the end (prompt-level).
3. **build-pipeline** — the **real dev-team `/plan`→`/build`** workflow (plugin
   loaded per cell).

**Findings:**

| | Correctness | Test quality | Cost (median total) | Notes |
|---|---|---|---|---|
| **test-first** | 100% (36/36) | 100% cov, 1.0 mutation | **$0.117** | cheapest; best to change |
| **test-after** | 100% (36/36) | 100% cov, 1.0 mutation | $0.132 (+12%) | |
| **build-pipeline** | **79% (19/24)** | 100% cov, 1.0 mutation | **$0.341 (+191%)** | 5 cells stalled at the plan-approval gate |

- **Test-first is the cheapest at equal correctness and equal test quality** — it
  was cheaper to *change* in **5/6** tasks (median **−28%** Stage-2 cost) and
  cheaper overall in **4/6** (median **−11%**).
- **Test quality was identical across all three arms** — every measurable cell
  hit 100% self-coverage and killed every seeded mutant. These katas are too
  small for test thoroughness to separate the workflows.
- **The `/build` pipeline cost ~3× for no measurable correctness or quality
  benefit on tasks this size**, and headlessly **stalled 21% of the time at the
  `/plan` human-approval gate** (a methodology artifact — see below — not bad
  code; where it completed, quality matched the cheaper arms).
- Everything here is **directional, not conclusive**: n = 6 tasks is underpowered
  (power analysis implies **~11–15 tasks**), and the cost edge is significant only
  one-sided and borderline.

## Methodology (concise)

Paired, multi-arm, repeated-trial, two-stage (full design in the linked doc).
Each cell ran in its own ephemeral git worktree **and** its own scratch `$HOME`,
dispatched as a fresh `claude -p --output-format json` (verified cost/tokens/turns;
no session resume). **Stage 2** applied a withheld change seeded from the Stage-1
**files only**. **Acceptance tests were hidden** during the build and injected
only at grading, so each arm had to write its own tests against the prose spec.

- **Trials:** instruction arms 3, build-pipeline 2 (it is ~10× the cost/time).
- **Sensors:** verified cost; `self_coverage` (coverage.py, prod files only); a
  built-in **AST mutation** check (flip arithmetic/compare/bool operators, re-run
  the agent's own tests; survivors = weak assertions); agent-test-file count.
- **build-pipeline arm:** each cell's `$HOME` was seeded from a plugin-enabled
  `.claude` template so `/plan` and `/build` load; the prompt drove the plugin
  pipeline and asked it to work autonomously.
- **Isolation held:** 1 contamination flag in 96 cells (a single high-turn-count
  note on a build-pipeline cell), no cost/context bleed.

## Results

### Median total cost ($) per task × arm

| Task | test-first | test-after | build-pipeline |
|---|---|---|---|
| caesar | 0.1035 | 0.1222 | 0.3548 |
| fizzbuzz | 0.1282 | 0.1740 | 0.4201 |
| rle | 0.0953 | 0.2069 | 0.3124 |
| roman | 0.1363 | 0.1317 | 0.3191 |
| rpn | 0.1142 | 0.1094 | 0.3276 |
| word-tally | 0.1200 | 0.1314 | 0.7643 |
| **arm median** | **0.1171** | **0.1315** | **0.3412** |

### Cost broken out (arm medians)

| Stage | test-first | test-after | build-pipeline |
|---|---|---|---|
| build | 0.0507 | 0.0518 | 0.2206 (~4×) |
| change | 0.0576 | 0.0803 | 0.1366 (~2.3×) |
| build turns (median) | 9.5 | 8.5 | **29** |

### Test-first vs test-after (paired, median)

| Task | Δ total $ | Δ change $ |
|---|---|---|
| caesar | −0.0188 | −0.0072 |
| fizzbuzz | −0.0458 | −0.0411 |
| rle | −0.1115 | −0.0876 |
| roman | +0.0047 | +0.0065 |
| rpn | +0.0047 | −0.0076 |
| word-tally | −0.0114 | −0.0246 |
| **TF wins** | **4/6** | **5/6** |

Significance (n=6): change-cost Wilcoxon W⁺=1 → one-sided ≈0.03 (borderline),
two-sided not significant; total cost not significant. Power → ~11 (change) /
~15 (total) tasks needed.

### Test quality (build stage, where measurable)

| Arm | self-coverage (median) | mutation score (median) | measurable cells |
|---|---|---|---|
| test-first | 100% | 1.0 | 12/18 |
| test-after | 100% | 1.0 | 18/18 |
| build-pipeline | 100% | 1.0 | 7/12 |

Identical. On single-function katas, all three workflows produce saturated suites.

## The `/build` arm's 79% pass rate is an approval-gate artifact

The 5 failed build-pipeline cells did **not** produce wrong code — they **stalled
at the `/plan` human-approval gate**. Their final output is literally *"Do you
approve this plan to begin implementation?"*; `/build` then never ran, so the
module stayed a stub and the hidden acceptance import failed. The signature is
clear in the turn counts:

- **failed cells:** 7, 13, 14, 14, 23 turns (halted early at the gate)
- **passed cells:** 14–54 turns (pushed through the gate and implemented)

The small model (haiku) **inconsistently honored** the "work autonomously, do not
wait for approval" instruction. This is a property of running an
approval-gated, interactive pipeline in fully headless mode — **not evidence that
`/build` writes worse code.** A clean build-pipeline comparison must bypass the
gate (an explicit auto-approve/non-interactive flag) and ideally use a stronger
model. Treat the 79% as "headless-autonomy reliability," not "code correctness."

## What we can and cannot conclude

**Can say (directionally, this scale/model):**
- At equal correctness and equal test quality, **test-first is the cheapest
  workflow**, with its clearest edge in **changeability** (Stage-2 cost).
- The **`/build` pipeline's planning/review overhead (~3× cost, ~3× turns) buys
  no measurable correctness or test-quality improvement on tasks this small.**
- **Test thoroughness does not separate the workflows here** — the tasks are too
  small; cost is the only axis that discriminates.

**Cannot say:**
- That any difference is **statistically established** (n=6, underpowered).
- That `/build` is worse in general — its value (catching design/quality issues
  via planning + review) should appear on **larger, multi-behavior features**,
  which this corpus deliberately lacks, and its headless pass rate here is
  depressed by the approval-gate artifact.

## Limitations

1. **Underpowered** — 6 tasks; ~11–15 needed.
2. **Model = haiku-4.5**, one model; effects may differ on a stronger model.
3. **Tiny single-function katas** — saturate the quality sensors; only cost
   separates. The design wants ≥5–8 scenarios per task.
4. **build-pipeline confound** — headless approval-gate stalls (21%) and possible
   under-use of the pipeline's review agents; not a clean read of `/build`.
5. **Mutation operator set is small**; a handful of cells were un-measurable.

## Reproducibility

```bash
# instruction arms (test-first, test-after), 3 trials
python3 scripts/run_tdd_experiment.py --only <6 tasks> --trials 3 \
  --model claude-haiku-4-5-20251001 --out metrics/campaign.jsonl

# build-pipeline arm, 2 trials, plugin-enabled HOME template
python3 scripts/run_tdd_experiment.py --arm build-pipeline --only <6 tasks> \
  --trials 2 --model claude-haiku-4-5-20251001 \
  --build-home-template /path/to/plugin-home --out metrics/build.jsonl
```

Approx. spend this campaign: test-first $2.13, test-after $2.60, build-pipeline
$5.00 (≈ **$9.7** for 96 dispatches).

## Recommendation / next steps

1. **For small, well-specified features, prefer test-first** — cheapest, equal
   quality, easier to change; reserve the full `/build` pipeline for larger or
   higher-risk work where planning + review earn their cost.
2. To make this **conclusive**: scale to **~12–15 larger, multi-behavior tasks**
   (so test quality can separate), at 3–5 trials, on a fixed stronger model.
3. **Re-run the build-pipeline arm with the approval gate bypassed** (non-
   interactive auto-approve) so its pass rate reflects code quality, not headless
   gating — then the three-way cost/quality comparison is clean.
4. Widen the mutation operator set and fix the few un-measurable cells.
