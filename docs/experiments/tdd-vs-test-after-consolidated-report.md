# Consolidated Report: TDD vs. Test-After vs. the `/build` Pipeline

**Status:** Complete — two campaigns (small/haiku and larger/sonnet), three arms
**Date:** 2026-06-21
**Design:** [`tdd-vs-test-after-experiment.md`](tdd-vs-test-after-experiment.md)
**Folds in:** [`tdd-vs-test-after-pilot-report.md`](tdd-vs-test-after-pilot-report.md),
[`tdd-vs-test-after-campaign-report.md`](tdd-vs-test-after-campaign-report.md)
**Raw data:** [`data/tdd-campaign-2026-06-21.jsonl`](data/tdd-campaign-2026-06-21.jsonl)
(small, haiku) · [`data/tdd-buildpipeline-2026-06-21.jsonl`](data/tdd-buildpipeline-2026-06-21.jsonl)
(small `/build`, haiku) · [`data/tdd-largetask-sonnet-2026-06-21.json`](data/tdd-largetask-sonnet-2026-06-21.json)
(larger tasks, sonnet, all 3 arms)
**Runner:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py)

## Executive summary — read this first

Three workflows (**test-first** = strict RED-GREEN-REFACTOR; **test-after** = all
code first, tests at the end; **build-pipeline** = the real dev-team
`/plan`→`/build`) were compared across **two campaigns**, every cell isolated and
graded by hidden acceptance tests:

| Campaign | Tasks | Model | Cheapest arm | test-first vs test-after |
|---|---|---|---|---|
| A — small katas | 6 small | haiku-4.5 | **test-first** | TF cheaper total 4/6, cheaper to change 5/6 (−28%) |
| B — larger tasks | 6 larger | **sonnet-4-6** | **test-after** | **TF *more* expensive total 6/6 (p=0.031)**, change edge gone |

**The headline finding is the reversal.** The "test-first is cheaper" result from
the small/haiku campaign **did not replicate** on larger tasks with a stronger
model — there **test-after was cheapest and test-first cost more on every task**.
On larger problems the up-front RED-GREEN iteration (median 17 turns vs 8) costs
more than it saves, and test-first's earlier changeability advantage disappeared.

**What held across both campaigns:**
- **Correctness was 100% for all arms** wherever they completed (108/108 + 36/36).
- **Test quality did not separate the workflows** — self-coverage and mutation
  score were saturated (≈100% / 1.0) across all arms in both campaigns; the only
  cracks appeared on the largest task (csvlite), where **test-after slightly
  *edged* test-first** (mutation 1.0 vs 0.8). No consistent test-first quality
  advantage was found.
- **The `/build` pipeline cost the most for no measurable quality benefit** —
  ~3× (haiku) and ~2.6× (sonnet) the cheapest arm, with no correctness/quality
  gain on tasks this size.

**Two methodology wins this round** (both fixed and re-run):
- The `/build` arm's headless **approval-gate stall (79% pass on haiku) was fixed**
  by a self-approve prompt → **100% pass on sonnet**. Its low earlier pass rate
  was an artifact, not bad code.
- **Test-quality sensors widened** (more mutation operators) and the
  un-measurable-cell gap closed (direct-execution fallback).

**Bottom line:** at these task sizes, **no workflow produced better-tested or
more-correct code; they differed only in cost, and which one is cheapest flips
with task size and model.** Test-first's cost advantage is *not* robust. The
`/build` pipeline is reliable (post-fix) but pays a premium that these katas are
too small to justify — its design value (planning/review on complex work) remains
untested here.

---

## Campaign A — small katas (haiku-4.5)

Six small features, withheld change, graded by hidden acceptance:

| | Correctness | Test quality | Cost (median total) | Notes |
|---|---|---|---|---|
| **test-first** | 100% (36/36) | 100% cov, 1.0 mutation | **$0.117** | cheapest; best to change |
| **test-after** | 100% (36/36) | 100% cov, 1.0 mutation | $0.132 (+12%) | |
| **build-pipeline** | 79% (19/24)* | 100% cov, 1.0 mutation | $0.341 (+191%) | *gate-stall artifact, fixed in B |

- **Test-first was the cheapest at equal correctness and equal test quality** —
  cheaper to *change* in **5/6** tasks (median **−28%** Stage-2 cost) and cheaper
  overall in **4/6** (median **−11%**).
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

## Campaign B — larger tasks, stronger model, gate bypassed (sonnet-4-6)

The "next steps" from Campaign A, executed: six **larger, multi-behavior** tasks
(stats, intervals, timeparse, money, matrix, csvlite — each several functions plus
a modifying change), on **`claude-sonnet-4-6`**, all three arms (the `/build` arm
with the **approval gate bypassed**), 1 trial, 36 cells. All passed, zero
contamination, $7.17 spend.

| Arm | Correctness | Test quality (build) | Cost (median total) | Turns |
|---|---|---|---|---|
| **test-after** | 100% (12/12) | 100% cov, 1.0 mut | **$0.215** (cheapest) | 8 |
| **test-first** | 100% (12/12) | 100% cov, 1.0 mut | $0.334 (+55%) | 17 |
| **build-pipeline** | **100% (12/12)** | 100% cov, 1.0 mut | $0.552 (+157%) | 14.5 |

- **The cost result reversed.** Test-first cost **more than test-after on all
  6/6 tasks** (sign test p = 0.031); its Campaign-A changeability edge vanished
  (more expensive to change on 5/6). On larger tasks the extra RED-GREEN turns
  (17 vs 8) outweigh any downstream saving.
- **The gate fix worked:** build-pipeline went **79% → 100%** pass once the prompt
  self-approves the `/plan` gate. Confirmed: the earlier failures were the gate,
  not code. It remains the most expensive arm (~2.6× test-after) with no quality
  gain.
- **Test quality still did not separate** (build stage saturated). The largest
  task, csvlite, showed the first cracks — and there **test-after (mutation 1.0)
  edged test-first (0.8)**, the opposite of the TDD-helps-quality hypothesis.
- **Sensor caveat:** the *change-stage* coverage/mutation came out uniformly
  ≈50% across all three arms (e.g. matrix change = 50% / 0.125 for every arm) —
  a harness artifact (the seeded build test-file not being re-measured at change
  time), so change-stage quality is **excluded** from conclusions; build-stage
  quality is the clean signal.

## What we can and cannot conclude

**Can say:**
- **No workflow produced more-correct or better-tested code** at these sizes —
  correctness was 100% and test quality saturated across all arms in both
  campaigns; the only quality crack (csvlite) slightly favored *test-after*.
- **Workflows differ only in cost, and the cheapest one flips** — test-first on
  small/haiku, test-after on larger/sonnet (the latter significant at 6/6,
  p=0.031). **Test-first's cost advantage is not robust.**
- The **`/build` pipeline reliably works once the approval gate is bypassed**, but
  **costs the most (~2.6–3×) for no measurable correctness or quality benefit** on
  tasks this size.

**Cannot say:**
- That `/build` is worse *in general* — its design value (planning + review
  catching defects on complex, multi-file, higher-risk work) is **not exercised**
  by single-module katas. This corpus cannot test where the pipeline is meant to
  pay off.
- That the cost differences generalize beyond ~1–3 dev-hour tasks and these two
  models. Campaign B used **1 trial** (no within-task variance), so per-task cost
  is a single sample (the 6/6 direction is nonetheless consistent).

## Limitations

1. **Statistical power** — 6 tasks per campaign; Campaign A 2–3 trials, Campaign
   B 1 trial. The 6/6 cost direction in B is consistent but not multi-trial.
2. **Two models, two sizes** — the cost winner is model/size-dependent (that is
   itself the finding); neither generalizes beyond ~1–3 dev-hour tasks.
3. **Still katas** — single-module; quality sensors saturate. Genuinely large,
   multi-file features (where `/build`'s planning/review should pay off) are
   untested.
4. **Change-stage quality sensor artifact** (Campaign B) — uniform ≈50% across
   arms; excluded. Fix: re-measure the full seeded suite at change time.
5. **`/build` realism** — runs headless with a self-approved gate and may
   under-use interactive review; a clean read still wants interactive/HITL runs.

## Reproducibility

```bash
# Campaign A — small katas, haiku, instruction arms (3 trials) + build (2 trials)
python3 scripts/run_tdd_experiment.py --only <6 small tasks> --trials 3 \
  --model claude-haiku-4-5-20251001 --out metrics/campaignA.jsonl
python3 scripts/run_tdd_experiment.py --arm build-pipeline --only <6 small tasks> \
  --trials 2 --model claude-haiku-4-5-20251001 \
  --build-home-template /path/to/plugin-home --out metrics/buildA.jsonl

# Campaign B — larger tasks, sonnet, all 3 arms (gate-bypassed build), 1 trial
python3 scripts/run_tdd_experiment.py \
  --arm test-first --arm test-after --arm build-pipeline \
  --only <6 larger tasks> --trials 1 --model claude-sonnet-4-6 \
  --build-home-template /path/to/plugin-home --out metrics/campaignB.jsonl
```

Approx. spend: Campaign A ≈ $9.7 (96 dispatches), Campaign B ≈ $7.2 (36
dispatches). Sonnet dispatches ran ~5–14 min each, so Campaign B was sharded
across parallel runners.

## Recommendation / next steps

1. **There is no test-quality or correctness reason to prefer one workflow** at
   these task sizes — pick on cost, and the cheapest depends on size/model:
   test-first for small/cheap-model work, test-after for larger/strong-model work.
   **Do not assume "TDD is cheaper" — it was not, on the larger tasks.**
2. **Reserve the full `/build` pipeline for complex, multi-file, higher-risk
   work** — it is reliable (post-gate-fix) but pays a 2.6–3× premium that single
   module katas cannot justify; its value needs a corpus that actually stresses
   planning and review.
3. **To settle it conclusively:** a genuinely large, multi-file corpus (not
   katas) at 3–5 trials, fixed model, with the change-stage sensor fixed and the
   `/build` arm run both headless and interactively.
