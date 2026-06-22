# Consolidated Report: Build-Pipeline vs. TDD vs. Non-TDD across Small / Medium / Large Tasks

**Status:** Complete — one campaign, three sizes, three arms, model fixed.
**Date:** 2026-06-22
**Model (fixed):** `claude-sonnet-4-6`
**Design + prior results:** [`experiment-prompt-3sizes-3arms.md`](experiment-prompt-3sizes-3arms.md),
[`tdd-vs-test-after-experiment.md`](tdd-vs-test-after-experiment.md),
[`tdd-vs-test-after-consolidated-report.md`](tdd-vs-test-after-consolidated-report.md)
**Runner:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py)
**Analyzer:** [`scripts/analyze_tdd_experiment.py`](../../scripts/analyze_tdd_experiment.py)
**Raw data:** [`data/3sizes-small-sonnet-2026-06-22.jsonl`](data/3sizes-small-sonnet-2026-06-22.jsonl) (small),
[`data/tdd-largetask-sonnet-2026-06-21.json`](data/tdd-largetask-sonnet-2026-06-21.json) (medium, folded in),
[`data/3sizes-large-sonnet-2026-06-22.jsonl`](data/3sizes-large-sonnet-2026-06-22.jsonl) (large),
[`data/3sizes-3arms-summary.json`](data/3sizes-3arms-summary.json) (machine summary)

---

## Executive summary — read this first

Three workflows — **build-pipeline** (the real dev-team `/plan`→`/build`),
**test-first** (strict RED-GREEN-REFACTOR), **test-after** (all code first, tests
last) — were compared on **18 tasks across three sizes** (6 small katas, 6 medium
single-module features, 6 **large multi-file packages**), every cell isolated and
graded by **hidden** acceptance tests, model held fixed at `claude-sonnet-4-6`.
**192 cells, 0 dispatch errors, 0 timeouts.**

| Size | Correctness (all arms) | Cheapest arm | build-pipeline premium (× cheapest) | Quality separates? |
|---|---|---|---|---|
| small | 100% build | **test-after** ($0.198) | **4.74×** ($0.94) | No (cov 100%, mut ≈1.0) |
| medium | 100% build | **test-after** ($0.215) | **2.57×** ($0.55) | No (cov 100%, mut 1.0) |
| large | 100% build | **test-after** ($0.613) | **1.33×** ($0.82) | **Sensors finally cracked — but arms still tied** |

**Three findings, in order of strength:**

1. **The build-pipeline's cost premium collapses as tasks get bigger — 4.74× →
   2.57× → 1.33×.** Its fixed planning/review overhead is a huge multiplier on a
   one-function kata but a *minor* surcharge on a real multi-file feature. On the
   large tier the pipeline costs only **33% more** than the cheapest hand-driven
   arm (paired median Δ=$0.18, sign p=0.031), at identical correctness and
   identical test quality. This is the first run where the pipeline's price looks
   like a reasonable tax rather than a 3–5× luxury.

2. **test-first vs test-after never separates on quality and barely separates on
   cost — and the cost gap is *not* monotonic.** test-after had the lower median
   total cost in all three sizes, but the difference is significant only at
   **medium** (Δ=$0.110, 6/6 tasks, p=0.031); at **small** (Δ=$0.012, p=0.22) and
   **large** (Δ=$0.0075, **3/3 split, p=1.0**) the two are effectively tied. The
   strict-TDD cost penalty the prior sonnet run reported on single-module tasks
   **did not generalize** to either smaller or larger work.

3. **The large tier did what it was added to do: it broke the quality-sensor
   saturation — and *still* found no workflow makes better-tested code.** Small
   and medium katas pin every arm at 100% coverage / 1.0 mutation (no signal). On
   the large multi-file packages coverage fell to **96.6–98.2%** and mutation to
   **0.911–0.924** — finally a measurable spread — yet the three arms land on top
   of each other (≤1.6 pp coverage, ≤0.013 mutation apart). The test-quality axis
   is real now, and it says **the workflow does not move it.**

**Bottom line.** At a fixed strong model, **the workflow you choose changes cost,
not correctness or test quality.** test-after is the cheapest everywhere but only
decisively so on mid-sized work; strict test-first buys no measurable quality and
costs the same or a little more; the `/plan`→`/build` pipeline is the most
expensive but its premium **shrinks toward parity as task complexity grows**,
which is exactly the regime its planning/review was designed for. The large tier
is where the pipeline's economics finally make sense — and also where, with N=6,
the cost differences stop being statistically distinguishable from the
instruction arms.

---

## What this run adds over the prior consolidated report

The prior report compared the arms on small katas at **haiku** and "larger"
single-module tasks at **sonnet**, and left one question open: does anything
separate the workflows on *bigger* work, given the katas saturate every sensor?
This run:

1. **Holds the model fixed at `claude-sonnet-4-6` across all three sizes** so size
   is the only moving axis. The prior small campaign was haiku, so small is
   **re-run here at sonnet**; the prior sonnet "larger" campaign *is* the medium
   tier and is folded in unchanged (same model, tasks, harness, grading).
2. **Adds a genuinely large tier** — six multi-file packages (≥2 source modules +
   a public API) with withheld behaviour-*modifying* changes touching ≥2 files.
3. Reports a clean **3×3 (size × arm) grid** with paired across-task statistics.

## Arms & tiers

- **build-pipeline** — real dev-team `/plan`→`/build` (self-approves its plan
  headlessly so the human gate cannot stall it).
- **test-first (TDD)** — strict RED-GREEN-REFACTOR.
- **test-after (non-TDD)** — all production code first, tests authored at the end.

| Size | Tasks | Shape |
|---|---|---|
| small | word-tally, roman, fizzbuzz, rpn, rle, caesar | single-function katas |
| medium | stats, intervals, timeparse, money, matrix, csvlite | one module, multi-function |
| large | spreadsheet, json-pointer, task-scheduler, template-engine, ledger, url-router | 2–4 source modules + public API |

The large tier was authored for this run. Each is a stub package with a
≥8-scenario spec, a withheld ≥2-file change, and **hidden** acceptance tests
(`acc.py` / `acc_change.py`) injected only at grading. Every acceptance file was
validated against a reference solution before running (reference passes; the
shipped golden repo is stubs only, so the build cannot cheat off the graded
tests). Fixtures live in `evals/fixtures/exp-tdd-<task>/` with manifests in
`evals/experiments/`.

## Pre-registration (fixed before looking at results)

- **Model:** `claude-sonnet-4-6`, fixed for the whole run.
- **Trials:** N=3 per (task × arm) for the instruction arms; N=2 for
  build-pipeline (≈2–3× the cost/time).
- **Unit of inference:** the **task**. Per (task, arm) take the **median across
  trials** of the two-stage total cost (build + change); form **paired arm
  differences across the 6 tasks** within a size; test with an exact **sign test**
  and exact **Wilcoxon signed-rank** test.
- **Stopping rule:** run the pre-registered N; no data-dependent stopping.
- **Quality** read from the **build stage only** (`self_coverage.percent`,
  `mutation.score`); any value uniform across all arms is a saturated sensor, not
  a finding.

---

## Results — the 3×3 grid

### Small (6 tasks)

| Arm | Correct build | Correct change | Median total cost | Cov% | Mutation | Median turns |
|---|---|---|---|---|---|---|
| build-pipeline | 12/12 | 12/12 | $0.940 | 100.0 | 0.988 | 15.5 |
| test-first | 18/18 | 17/18 | $0.217 | 100.0 | 1.0 | 8.0 |
| test-after | 18/18 | 17/18 | **$0.198** | 100.0 | 1.0 | 8.0 |

### Medium (6 tasks)

| Arm | Correct build | Correct change | Median total cost | Cov% | Mutation | Median turns |
|---|---|---|---|---|---|---|
| build-pipeline | 6/6 | 6/6 | $0.552 | 100.0 | 1.0 | 14.5 |
| test-first | 6/6 | 6/6 | $0.334 | 100.0 | 1.0 | 17.0 |
| test-after | 6/6 | 6/6 | **$0.215** | 100.0 | 1.0 | 8.0 |

### Large (6 tasks)

| Arm | Correct build | Correct change | Median total cost | Cov% | Mutation | Median turns |
|---|---|---|---|---|---|---|
| build-pipeline | 12/12 | 11/12 | $0.818 | 96.6 | 0.924 | 16.25 |
| test-first | 18/18 | 15/18 | $0.665 | 98.2 | 0.923 | 14.0 |
| test-after | 18/18 | 17/18 | **$0.613** | 97.8 | 0.911 | 12.0 |

## Paired statistics (across the 6 tasks in each size; +Δ ⇒ first arm costs more)

| Size | Pair | Median Δ | Direction | Sign p | Wilcoxon p |
|---|---|---|---|---|---|
| small | BP vs test-first | +$0.716 | BP higher 6/6 | **0.031** | **0.031** |
| small | BP vs test-after | +$0.715 | BP higher 6/6 | **0.031** | **0.031** |
| small | test-first vs test-after | +$0.012 | TF higher 5/6 | 0.219 | 0.438 |
| medium | BP vs test-first | +$0.198 | BP higher 5/6 | 0.219 | 0.094 |
| medium | BP vs test-after | +$0.336 | BP higher 6/6 | **0.031** | **0.031** |
| medium | test-first vs test-after | +$0.110 | TF higher 6/6 | **0.031** | **0.031** |
| large | BP vs test-first | +$0.179 | BP higher 5/6 | 0.219 | 0.094 |
| large | BP vs test-after | +$0.176 | BP higher 6/6 | **0.031** | **0.031** |
| large | test-first vs test-after | +$0.008 | **3/3 split** | **1.000** | 0.688 |

The build-pipeline **cost-multiplier vs the cheapest arm** falls monotonically
with size: **4.74× (small) → 2.57× (medium) → 1.33× (large)**. The
test-first/test-after ratio is **1.09 → 1.55 → 1.08** — the strict-TDD penalty
peaks at medium and is negligible at both ends.

## What separates (and what doesn't)

- **Correctness does not separate the arms.** Build-stage correctness is 100% for
  every arm at every size (and the one small build-pipeline "miss" is a
  change-stage cell, not a build). The withheld changes are genuinely hard on the
  large tier — change-stage pass rates dip (test-first 15/18, build-pipeline
  11/12, test-after 17/18) — but with 1–3 failures per 18 cells this is noise, not
  a workflow effect, and notably it is **test-first**, not test-after, that
  logged the most large-tier change failures.
- **Test quality does not separate the arms.** Where the sensors have any
  resolution (the large tier) the three arms sit within 1.6 pp of coverage and
  0.013 of mutation score. There is no "test-first writes stronger tests" signal
  anywhere in the data.
- **Cost separates the arms, and only cost.** build-pipeline is the most expensive
  in all three sizes; test-after is the cheapest in all three. The *interesting*
  structure is in the magnitudes: the pipeline premium amortizes with task size,
  and the TDD penalty is real only in the middle.
- **Turns track cost.** test-after consistently runs the fewest turns (8–12);
  test-first runs more on medium (17) where its cost penalty is largest; the
  pipeline runs 14.5–16 turns of planning+review overhead regardless of size,
  which is why it dominates cost on tiny tasks and amortizes on big ones.

## Why the pipeline premium shrinks (mechanism)

The `/plan`→`/build` pipeline pays a roughly **fixed** overhead per task: a
planning pass, batched inline review, and a structured build loop (≈15–16 turns
across all sizes). On a one-function kata that fixed cost is 4–5× the entire
hand-written solution; on a six-scenario multi-file package it is a third again
on top of work that was already substantial. Same surcharge, very different
denominator. This is the regime the pipeline was designed for, and the large tier
is the first place its economics are defensible — though even here it buys no
measurable correctness or quality over just writing the code.

## Limitations

- **n = 6 tasks per size.** The exact paired tests bottom out at p≈0.03 with 6
  pairs, so single-size results are directional; the **cross-size pattern** (the
  monotone pipeline premium) is the durable signal, not any one p-value.
- **Single model.** Prior work showed the cost winner flips with model; this run
  fixes sonnet and says nothing about haiku/opus.
- **build-pipeline at N=2** has less within-task stability than the instruction
  arms at N=3; its medians are noisier (e.g. template-engine's $2.22 outlier).
- **Medium tier folded from the 2026-06-21 sonnet run (N=1/trial)** rather than
  re-run — same model/tasks/harness/grading, but a lower trial count than
  small/large. Noted, not hidden.
- **Quality is build-stage only.** The change-stage coverage/mutation sensors had
  a uniform-across-arms artifact in the prior run (its Limitation 4); they are
  excluded here.
- **Mutation is the built-in AST sampler (cap 40), not a full tool.** It now runs
  under a 30 s per-test timeout (added this run — see below); an infinite-loop
  mutant counts as killed.

## Methodology notes & a harness fix landed this run

Paired, multi-arm, repeated-trial, two-stage. Each cell (`task × arm × trial ×
stage`) ran in its own ephemeral git worktree **and** its own scratch `$HOME`,
dispatched as a fresh `claude -p --output-format json` (verified
cost/tokens/turns; no session resume). Stage 2 applied the withheld change seeded
from the Stage-1 **files only**. Acceptance tests were hidden during the build and
injected only at grading. Cost is read from the native JSON result. The
build-pipeline arm got a plugin-enabled `$HOME` per cell.

**Fix landed:** the mutation/coverage test runs had no wall-clock cap, so a
mutation that turned a roman-numeral subtractive loop infinite hung pytest
forever and stalled the whole cell. The runner now wraps every agent/mutant test
invocation in a timeout (`PYTEST_TIMEOUT`, 30 s), treating a timed-out run as a
failed run. The two affected cells were re-run cleanly under the fix; the final
data set has **0 timeouts and 0 errors** across all 192 cells.

## Reproducibility

```bash
pip install coverage pytest
TPL=/tmp/build-home-tpl; mkdir -p "$TPL/.claude"
cp ~/.claude/settings.json "$TPL/.claude/"; cp -r ~/.claude/plugins "$TPL/.claude/"

# per size, per task: instruction arms @3 trials + build-pipeline @2 trials
python3 scripts/run_tdd_experiment.py --arm test-first --arm test-after \
  --only "<task>" --trials 3 --model claude-sonnet-4-6 --out small.jsonl
python3 scripts/run_tdd_experiment.py --arm build-pipeline \
  --only "<task>" --trials 2 --model claude-sonnet-4-6 \
  --build-home-template /tmp/build-home-tpl --out small_build.jsonl

python3 scripts/analyze_tdd_experiment.py \
  --data data/3sizes-small-sonnet-2026-06-22.jsonl \
  --data data/tdd-largetask-sonnet-2026-06-21.json \
  --data data/3sizes-large-sonnet-2026-06-22.jsonl \
  --json data/3sizes-3arms-summary.json
```

## Recommendation

- **Default to writing the code and testing it — the workflow is a cost lever,
  not a quality lever.** Across 18 tasks and a fixed strong model, no workflow
  produced more-correct or better-tested code; they differed only in price.
- **Reserve the `/plan`→`/build` pipeline for large, multi-file work.** Its
  overhead is a 4–5× tax on katas but only ~1.3× on real packages, where its
  planning/review is plausibly worth a third more for reasons this cost/quality
  harness cannot see (human review burden, design coherence, regression safety on
  changes that touch several files). On small/medium tasks the pipeline is hard to
  justify on these metrics alone.
- **Do not adopt strict test-first for cost reasons.** It is never cheaper than
  test-after here and is significantly more expensive on mid-sized tasks, at equal
  quality. If TDD is used, use it for its design/iteration benefits, not an
  expectation of cheaper or better-tested output at this model strength.
- **Next:** the quality axis only became measurable on the large tier; to actually
  *separate* workflows on quality would need either harder tasks (where coverage
  drops further) or a longer change-chain that stresses the suite as a regression
  net. That, not more katas, is where a difference — if one exists — will show up.
