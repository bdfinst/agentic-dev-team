# Refactoring cadence & authorship — pre-run power analysis

**Status: the experiment as written in
[`experiment-prompt-refactor-granularity.md`](experiment-prompt-refactor-granularity.md)
is underpowered for its headline question. Revise the design before spending model
budget.** Reproduce with `python3 scripts/power_calc_refactor_granularity.py` (no model
cost — reads the existing `tdd-pays` run1+run2 data).

## What the prompt assumed vs. what the pilot data says

The prompt's headline is a TOST on cumulative blast radius (continuous vs one-shot refactor)
at a **±5% margin**, expecting **N ≈ 12–15 trials/cell**. The existing 4-task pilot data
(which produced the 664 vs 678 tie) does not support that N:

| quantity | value |
|---|---|
| grand mean cumulative blast radius | 701 lines |
| 5% effect target | **35 lines** |
| paired diff (tdd-refactor − test-after-refactor), per task×clarity | mean **+36**, SD **235** |
| paired units available (4 tasks × 2 clarities) | **8** |
| paired units needed for 80% power @ 5% | **352** |
| unpaired per-cell N needed (pooled refactor SD = 119) | **181/cell** |

**The binding constraint is task count, not trials.** The unit of inference is the
task×clarity cell; there are only 8. The per-task×clarity differences swing from **−238 to
+381 lines** — ~7× the effect we want to detect, and they *flip sign with clarity*. Adding
trials per cell shrinks each cell's median noise but adds no paired units, so it cannot
rescue the main-effect test. Detecting a 5% main effect needs **dozens of tasks**, not
12–15 trials.

## But the data contains large, detectable effects — just not the 5% main effect

The 664-vs-678 "tie" is an artifact of averaging a sign-flipping, heteroscedastic
distribution. Cell-by-cell the refactor arms are not behaving equivalently at all:

**1. Free-refactor is wildly unstable (variance effect, ~7×):**

| arm | within-cell SD of cumulative blast |
|---|---|
| tdd-refactor (continuous, frozen-ish) | 29.5 |
| test-after (no refactor) | 24.1 |
| tdd-no-refactor | 14.5 |
| **test-after-refactor (one-shot, free)** | **208.1** |

**2. Free-refactor destroys edge coverage under vague specs (EDGE effect, huge):**

| arm | EDGE pass rate, vague spec |
|---|---|
| test-after | 66.7% |
| bduf | 41.7% |
| tdd-refactor | 33.3% |
| ship / tdd-no-refactor | 25.0% |
| **test-after-refactor** | **0.0%** |

These are exactly the safety-net hypothesis (safety-net erosion) and authorship-interaction hypothesis (clarity×protection interaction)
mechanisms the prompt hypothesized — and their effect sizes (7× variance ratio, 0% vs 67%
EDGE) are far above 5%, so they are detectable at modest N. What is *not* detectable at 4
tasks is the ±5% blast-radius main effect framed as the headline.

## Recommendation — revise before running

1. **Demote the 5% blast-radius TOST to a secondary endpoint** that will likely report
   "inconclusive at this scale," and **promote the real effects to primary**: (a) the
   free-vs-frozen *variance/stability* contrast, (b) EDGE collapse under free+vague, (c) the
   test-LOC churn → blast-radius mediation. These are the questions the pilot says are
   answerable, and they directly settle safety-net hypothesis/authorship-interaction hypothesis.
2. **If the 5% main effect must stay primary, the cost is task count, not trials.** Author
   roughly **20–40 pays-style tasks** (the prompt's "reuse the same 4 tasks" is the binding
   limitation). That is a large authoring effort and a much larger campaign.
3. **Trials/cell ≈ 10–15 is still justified** — not for the main effect, but to pin down the
   high-variance free-refactor cells (SD 208 needs ~10+ trials for a stable median) and to
   power the within-cell variance comparison.

The constructive read: the experiment is worth running, but re-aimed at the variance, EDGE,
and churn-mediation endpoints (large, real, on the current 4 tasks with ~12 trials), with
the blast-radius equivalence claim reported honestly as underpowered unless the task corpus
is expanded.
