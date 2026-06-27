# Consolidated Report: Build-Pipeline vs. TDD vs. Non-TDD across Small / Medium / Large Tasks

**Status:** Complete — one campaign, three sizes, three arms, model fixed.
**Date:** 2026-06-22
**Model (fixed):** `claude-sonnet-4-6`
**Design + prior results:** [`01-experiment-prompt-3sizes-3arms.md`](01-experiment-prompt-3sizes-3arms.md),
[`tdd-vs-test-after-experiment.md`](tdd-vs-test-after-experiment.md),
[`tdd-vs-test-after-consolidated-report.md`](tdd-vs-test-after-consolidated-report.md)
**Runner:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py)
**Analyzer:** [`scripts/analyze_tdd_experiment.py`](../../scripts/analyze_tdd_experiment.py)
**Raw data:** [`data/3sizes-small-sonnet-2026-06-22.jsonl`](data/3sizes-small-sonnet-2026-06-22.jsonl) (small),
[`data/tdd-largetask-sonnet-2026-06-21.json`](data/tdd-largetask-sonnet-2026-06-21.json) (medium, folded in),
[`data/3sizes-large-sonnet-2026-06-22.jsonl`](data/3sizes-large-sonnet-2026-06-22.jsonl) (large),
[`data/3sizes-3arms-summary.json`](data/3sizes-3arms-summary.json) (cost/quality summary),
[`data/3sizes-review-findings.json`](data/3sizes-review-findings.json) (review-agent findings, large tier)

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
   saturation — and the *coverage/mutation* axis still found no workflow makes
   better-tested code.** Small and medium katas pin every arm at 100% coverage /
   1.0 mutation (no signal). On the large multi-file packages coverage fell to
   **96.6–98.2%** and mutation to **0.911–0.924** — finally a measurable spread —
   yet the three arms land on top of each other (≤1.6 pp coverage, ≤0.013 mutation
   apart). On *that* axis, the workflow does not move it.

4. **A third quality lens — running the dev-team review agents over each arm's
   produced code — *does* separate them, and it favors the pipeline.** Coverage
   and mutation are blind to structure/complexity/duplication; the review agents
   are not. Re-generating one solution per arm for the 6 large tasks and running a
   6-agent panel (structure, complexity, naming, performance, security, test)
   over each, the **build-pipeline produced the fewest review-grade findings
   (weighted 67, median 10.5/task) — cleaner than test-first (108, 19.0) and
   test-after (91, 15.0) — and cleaner on 5 of 6 tasks** than either hand-driven
   arm (vs test-first sign p=0.06; vs test-after p=0.22). Its inline `/build`
   review step is the plausible cause. This is **directional, not conclusive**
   (n=6; the review agents show real run-to-run variance — see the section
   below), but it is the first quality signal in this whole line of experiments
   that points anywhere, and it points at the pipeline.

**Bottom line.** At a fixed strong model, **the workflow you choose changes cost
and review-grade structure, but not correctness or coverage/mutation test
quality.** test-after is the cheapest everywhere (decisively only on mid-sized
work); strict test-first is never cheaper and drew the most review findings; the
`/plan`→`/build` pipeline is the most expensive but its premium **shrinks toward
parity as task complexity grows** (4.7×→2.6×→1.3×) *and* its code is the cleanest
on review (5/6 large tasks). The large tier is where the pipeline's economics
finally make sense — a ~1.3× premium that now buys a directional but consistent
structural-quality edge — even though, with N=6, the cost differences there are
no longer statistically distinguishable from the instruction arms.

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
- **Coverage/mutation test quality does not separate the arms.** Where those
  sensors have any resolution (the large tier) the three arms sit within 1.6 pp of
  coverage and 0.013 of mutation score. There is no "test-first writes stronger
  tests" signal in the coverage/mutation data.
- **Review-grade quality *does* separate them (see the dedicated section).** The
  dev-team review agents find the build-pipeline's code cleanest (fewest weighted
  findings on 5/6 large tasks vs both hand-driven arms) — a signal coverage and
  mutation are structurally blind to. Directional at n=6, but consistent.
- **Cost separates the arms, and only cost.** build-pipeline is the most expensive
  in all three sizes; test-after is the cheapest in all three. The *interesting*
  structure is in the magnitudes: the pipeline premium amortizes with task size,
  and the TDD penalty is real only in the middle.
- **Turns track cost.** test-after consistently runs the fewest turns (8–12);
  test-first runs more on medium (17) where its cost penalty is largest; the
  pipeline runs 14.5–16 turns of planning+review overhead regardless of size,
  which is why it dominates cost on tiny tasks and amortizes on big ones.

## Third quality lens: review-grade defect density (large tier)

Coverage and mutation measure whether the *tests* pin the behavior; they are
blind to how the *production code* is structured. To probe that, one build-stage
solution per arm was **regenerated for the 6 large tasks** (kept on disk; the
experiment deletes its worktrees) using the harness's exact arm prompts, and a
fixed **6-agent review panel** — `structure-review`, `complexity-review`,
`naming-review`, `performance-review`, `security-review`, `test-review` — was run
over each. Findings are weighted **critical=4, high=3, medium=2, low=1**.

| Arm | Critical | High | Medium | Low | Findings | Weighted | Median/task |
|---|---|---|---|---|---|---|---|
| **build-pipeline** | 1 | 9 | 12 | 12 | **34** | **67** | **10.5** |
| test-after | 4 | 10 | 14 | 17 | 45 | 91 | 15.0 |
| test-first | 3 | 14 | 18 | 18 | 53 | 108 | 19.0 |

**Paired across the 6 tasks** (weighted findings; +Δ ⇒ first arm has *more*/worse findings):

| Pair | Median Δ | Cleaner arm wins | Sign p |
|---|---|---|---|
| build-pipeline vs test-first | −6.5 | build-pipeline in **5/6** | 0.0625 |
| build-pipeline vs test-after | −5.0 | build-pipeline in **5/6** | 0.219 |
| test-first vs test-after | +3.5 | test-after in 4/6 | 0.375 |

**Reading it:** the build-pipeline's code carried the lowest review-grade defect
density on 5 of 6 tasks against *both* hand-driven arms — the inline review step
inside `/build` is the obvious mechanism. test-after edged test-first (test-first
drew the most findings overall, largely from `complexity-review` — strict
RED-GREEN-REFACTOR left more long/deeply-nested functions on the
spreadsheet/template/router parsers). This is the **only quality axis in this
whole experiment line that points anywhere.**

**Trust it cautiously.** The review agents show real **run-to-run variance** on
near-identical code: `naming-review` scored the three arms 0 / 19 / 4 (weighted)
when the same magic-string token types exist in all three, and `test-review`
scored test-first's tests far harder (44) than the others (18 / 19), partly for
one over-specified assertion. Per-agent noise is large; the *aggregate* direction
(build-pipeline lowest on structure, complexity, performance, and test agents) is
what carries the signal, and at n=6 the sign tests are p≈0.06–0.4 — directional,
not conclusive. All 18 solutions were correct (they pass the hidden acceptance),
so these are *style/structure* findings, not bugs.

## Why the pipeline premium shrinks (mechanism)

The `/plan`→`/build` pipeline pays a roughly **fixed** overhead per task: a
planning pass, batched inline review, and a structured build loop (≈15–16 turns
across all sizes). On a one-function kata that fixed cost is 4–5× the entire
hand-written solution; on a six-scenario multi-file package it is a third again
on top of work that was already substantial. Same surcharge, very different
denominator. This is the regime the pipeline was designed for, and the large tier
is the first place its economics are defensible — a ~1.3× premium that, per the
review lens above, also buys directionally cleaner structure (it buys no
correctness or coverage/mutation edge, but the review agents do favor it).

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
- **The review lens is a separate, smaller study.** It regenerates **one**
  solution per (arm × large task) — N=1, not the 2–3 trials of the cost data — and
  grades it with review agents that have measurable run-to-run variance. Its 5/6
  build-pipeline result is the most interesting finding here and the least
  statistically settled; treat it as a hypothesis worth a powered follow-up
  (more trials per cell, multiple review passes averaged), not a conclusion.
  Findings are also self-graded by the same model family that wrote the code.
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

**Review lens (separate pass):** because the experiment deletes each cell's
worktree, the produced code is not retained. For the review-grade lens, one
build-stage solution per (arm × large task) was **regenerated and kept** with the
harness's exact arm prompts (`/tmp/gen_solutions.py`), then graded by the 6-agent
review panel; results are in
[`data/3sizes-review-findings.json`](data/3sizes-review-findings.json).

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

- **For cost and correctness, the workflow is a cost lever, not a quality lever.**
  Across 18 tasks and a fixed strong model, no workflow produced more-correct or
  better-*covered*/mutation-tested code; on those axes they differed only in price.
- **But review-grade quality is the exception, and it favors the pipeline.** On
  the large tier the `/plan`→`/build` pipeline's code carried the lowest
  review-grade defect density (cleaner on 5/6 tasks vs both hand-driven arms).
  Combined with its premium shrinking to ~1.3× on large work, this **strengthens
  the case for the pipeline on large, multi-file features**: you pay a third more
  and get measurably cleaner structure (directionally; n=6) at equal correctness.
  On small/medium katas the pipeline is still a 2.6–4.7× tax for code the review
  agents barely fault either way — hard to justify there.
- **Default to writing the code and testing it for small/medium work.** test-after
  is the cheapest arm everywhere and its code is no worse than test-first's on
  review (slightly better, in fact). Strict test-first is never cheaper and drew
  the most review findings here — use it for its design/iteration discipline, not
  an expectation of cheaper, better-tested, or cleaner output at this model
  strength.
- **Next:** the most interesting and least-settled result is the review-grade
  edge for the pipeline. A powered follow-up — multiple trials per (arm × task),
  several review passes averaged to beat reviewer variance, and ideally a
  human-graded subset — would confirm or kill it. The coverage/mutation axis, by
  contrast, needs *harder* tasks (where coverage drops further) or a longer
  change-chain to separate the arms at all; that, not more katas, is where any
  test-quality difference would surface.
