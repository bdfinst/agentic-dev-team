# Campaign Report: Test-First (TDD) vs. Test-After Workflow

**Status:** Complete — 6-task campaign with test-quality sensors
**Date:** 2026-06-21
**Supersedes:** [`tdd-vs-test-after-pilot-report.md`](tdd-vs-test-after-pilot-report.md) (2-task pilot)
**Design:** [`tdd-vs-test-after-experiment.md`](tdd-vs-test-after-experiment.md)
**Raw data:** [`data/tdd-campaign-2026-06-21.jsonl`](data/tdd-campaign-2026-06-21.jsonl) (72 rows)
**Runner:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py)

## TL;DR

72 dispatches (6 tasks × 2 arms × 3 trials × 2 stages) on `claude-haiku-4-5`,
all isolated, all green, zero contamination. **At equal correctness (72/72 pass)
and equal test quality (both arms saturate coverage and mutation), test-first was
consistently cheaper — most clearly on the follow-up change:**

- **Cheaper to change** in **5 of 6** tasks (median **−28%** change-stage cost).
- **Cheaper overall** in **4 of 6** tasks (median **−11%** total cost).
- **Test quality: a tie** — both arms hit ~100% self-coverage and 1.0 mutation
  score wherever measurable, on these small tasks.

The direction matches the hypothesis, but **n = 6 tasks is underpowered**: the
change-cost edge is significant only one-sided (Wilcoxon, borderline), total cost
is not significant, and the power analysis implies **~11–15 tasks** are needed.
**This is suggestive, not conclusive.** Total spend: **$4.73**.

## What changed since the pilot

1. **Corpus 2 → 6 tasks**: word-tally, roman, fizzbuzz, rpn, rle, caesar — each a
   small feature with a withheld Stage-2 change and hidden acceptance tests
   validated against reference solutions.
2. **Test-quality sensors wired** (the pilot's biggest gap):
   - **`self_coverage`** — branch coverage of the agent's production code by the
     agent's *own* tests (`coverage.py`, production files only).
   - **`mutation`** — a built-in **AST mutation** check: flip arithmetic /
     comparison / boolean / boolean-constant operators one at a time, re-run the
     agent's tests; a survivor is direct evidence of a weak or missing assertion.
   - Both run on the agent's suite **before** hidden acceptance tests are
     injected. Validated to discriminate (strong suite → 1.0; weak suite → 0.667
     with a survivor).
   - A pytest-runnable constraint is applied **equally to both arms** so the
     sensors can run; it does not touch the when-to-test variable.

## Methodology (delta from the design doc)

Paired, two-arm, repeated-trial, two-stage — full design in the linked doc. Each
cell ran in its own ephemeral worktree **and** its own scratch `$HOME`, dispatched
as a fresh `claude -p --output-format json` (verified cost/tokens/turns; no
session resume). Stage 2 was seeded from the Stage-1 **files only**. Acceptance
tests were hidden during the build and injected only at grading. Model held
constant at `claude-haiku-4-5`; 3 trials per (task × arm).

## Results

### Per task × arm (median of 3 trials)

| Task | Arm | Total $ | Build $ | Change $ | Self-cov % | Mutation |
|---|---|---|---|---|---|---|
| caesar | test-first | 0.1035 | 0.0479 | 0.0556 | 100 | 1.0 |
| caesar | test-after | 0.1222 | 0.0569 | 0.0628 | 100 | 1.0 |
| fizzbuzz | test-first | 0.1282 | 0.0468 | 0.0753 | 100 | 1.0 |
| fizzbuzz | test-after | 0.1740 | 0.0566 | 0.1164 | 100 | 1.0 |
| rle | test-first | 0.0953 | 0.0421 | 0.0529 | 100 | 1.0 |
| rle | test-after | 0.2069 | 0.0483 | 0.1405 | 100 | 1.0 |
| roman | test-first | 0.1363 | 0.0534 | 0.0829 | 100 | 1.0 |
| roman | test-after | 0.1317 | 0.0553 | 0.0764 | 100 | 1.0 |
| rpn | test-first | 0.1142 | 0.0671 | 0.0456 | 100 | n/a* |
| rpn | test-after | 0.1094 | 0.0467 | 0.0532 | 96.7 | 1.0 |
| word-tally | test-first | 0.1200 | 0.0604 | 0.0596 | 100 | n/a* |
| word-tally | test-after | 0.1314 | 0.0472 | 0.0842 | 100 | 1.0 |

\* `mutation = n/a`: the agent's own suite was not pytest-collectable at sensor
time (exit "no tests collected"), so the mutation baseline wasn't green and the
score is undefined. Measurable in **30 of 36** build cells; where measured, **both
arms scored 1.0**.

### Paired comparison (test-first − test-after, median)

| Task | Δ total $ | Δ change $ |
|---|---|---|
| caesar | −0.0188 | −0.0072 |
| fizzbuzz | −0.0458 | −0.0411 |
| rle | **−0.1115** | **−0.0876** |
| roman | +0.0047 | +0.0065 |
| rpn | +0.0047 | −0.0076 |
| word-tally | −0.0114 | −0.0246 |
| **test-first wins** | **4 / 6** | **5 / 6** |

### The four success properties

| Property | Result |
|---|---|
| **Easy to change** | test-first cheaper Stage-2 in **5/6** (median −28%). Strongest signal. |
| **Lower token cost** | test-first cheaper total in **4/6** (median −11%). |
| **Fully tested** | **tie** — both arms ~100% self-coverage, 1.0 mutation where measurable. |
| **Less rework** | proxy = build turns; **median 9 vs 9**, no difference at this size. |

## Statistical reading (honest)

- **Within-cell stability:** median CV of total cost across trials = **8.0%**
  (one noisy cell at 47%) — three trials give a reasonably stable per-cell median.
- **Significance (n = 6 tasks):**
  - Change cost: sign test p = 0.219; Wilcoxon W⁺ = 1 — **one-sided ≈ 0.03**
    (borderline), **two-sided not significant**.
  - Total cost: sign test p = 0.69; Wilcoxon W⁺ = 3 — **not significant**.
- **Power:** observed paired effect sizes give dz ≈ 0.87 (change), 0.74 (total) →
  **~11 tasks** (change) / **~15 tasks** (total) needed for 80% power. Six is
  short.

**Verdict against the pre-registered rule (§7):** **not met.** The rule requires
test-first to win on *all four* axes across tasks; here test quality is a tie and
total cost is not universally lower. So the outcome is the **trade-off result the
design anticipated as most likely**: test-first is **directionally cheaper at
equal correctness and equal test quality**, with the advantage concentrated in
**changeability**, but the margin is **not statistically established** at this
scale.

## Why "fully tested" came out a tie

These are single-function katas. On a problem this small a competent test-after
pass produces a suite as complete as a test-first one — 100% coverage and every
seeded mutant killed, for both arms. The test-quality axis only becomes
discriminating on larger features where weak assertions and missed branches have
room to appear (the design calls for ≥ 5–8 scenarios per task). The cost axis,
by contrast, already separates at this size.

## Limitations

1. **Underpowered** — 6 tasks; needs ~11–15. Directional, borderline one-sided.
2. **Model = haiku-4.5** — one model; effect may differ on a stronger model.
3. **Instruction-level TDD, not `/build`** — each cell ran without the plugin, so
   "test-first" was prompt-enforced, not gated by the plugin's RED-GREEN-REFACTOR.
4. **Tiny tasks** — saturate the test-quality sensors; cost is the only axis that
   separates here.
5. **Mutation operator set is small** (arithmetic/compare/bool/bool-const) and 2
   cells were un-measurable; coverage can be high with weak asserts, so treat the
   "tie" as "no detectable difference at this size," not proof of equivalence.

## Reproducibility

```bash
python3 scripts/run_tdd_experiment.py \
  --only exp-tdd-word-tally,exp-tdd-roman,exp-tdd-fizzbuzz,exp-tdd-rpn,exp-tdd-rle,exp-tdd-caesar \
  --trials 3 --model claude-haiku-4-5-20251001 \
  --run-root /tmp/camp-run --out metrics/tdd-experiment.jsonl
```

## To convert "suggestive" into "conclusive"

1. **Scale to ~12–15 tasks** (power says so) at 3–5 trials.
2. **Add larger, multi-behavior tasks** (≥ 5–8 scenarios, modifying changes) so
   the test-quality axis can actually separate.
3. **Add a third arm that invokes the real `/build` pipeline** (plugin active per
   cell) to test the *plugin* workflow, not just the TDD practice — the only
   remaining "next step" not yet done, deferred because per-cell plugin
   activation is a materially larger harness change.
4. Optionally widen the mutation operator set and fix the 2 un-measurable cells.
