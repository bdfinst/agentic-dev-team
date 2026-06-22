# Consolidated Report: Build-Pipeline vs. TDD vs. Non-TDD across Small / Medium / Large Tasks

**Status:** _DRAFT — campaign running; numbers filled on completion._
**Date:** 2026-06-22
**Model (fixed):** `claude-sonnet-4-6`
**Design + prior results:** [`experiment-prompt-3sizes-3arms.md`](experiment-prompt-3sizes-3arms.md),
[`tdd-vs-test-after-experiment.md`](tdd-vs-test-after-experiment.md),
[`tdd-vs-test-after-consolidated-report.md`](tdd-vs-test-after-consolidated-report.md)
**Runner:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py)
**Analyzer:** [`scripts/analyze_tdd_experiment.py`](../../scripts/analyze_tdd_experiment.py)
**Raw data:** [`data/3sizes-small-sonnet-2026-06-22.jsonl`](data/3sizes-small-sonnet-2026-06-22.jsonl),
[`data/3sizes-large-sonnet-2026-06-22.jsonl`](data/3sizes-large-sonnet-2026-06-22.jsonl),
[`data/tdd-largetask-sonnet-2026-06-21.json`](data/tdd-largetask-sonnet-2026-06-21.json) (medium tier, folded in)

---

## What this run adds over the prior consolidated report

The prior consolidated report compared the three workflows on two campaigns:
small katas at **haiku** and "larger" single-module tasks at **sonnet**. Its open
question was whether anything separates the workflows on *bigger* work, since the
katas saturated every quality sensor. This run:

1. **Holds the model fixed at `claude-sonnet-4-6` across all three sizes** so size
   is the only axis that moves (the prior small campaign was haiku, so it is
   **re-run here at sonnet**; the prior sonnet "larger" campaign is the
   **medium** tier and is folded in unchanged).
2. **Adds a genuinely large tier**: six **multi-file packages** (≥2 source modules
   + a public API) where planning/review can actually bite, each with a withheld
   behaviour-*modifying* change that touches ≥2 files.
3. Reports a clean **3×3 (size × arm) grid** with paired across-task statistics.

## Arms

- **build-pipeline** — the real dev-team `/plan`→`/build` pipeline (self-approves
  its plan headlessly so the human gate does not stall it).
- **test-first (TDD)** — strict RED-GREEN-REFACTOR.
- **test-after (non-TDD)** — all production code first, tests authored at the end.

## Task tiers (6 tasks each, all sonnet)

| Size | Tasks | Shape |
|---|---|---|
| small | word-tally, roman, fizzbuzz, rpn, rle, caesar | single-function katas |
| medium | stats, intervals, timeparse, money, matrix, csvlite | single module, multi-function |
| large | spreadsheet, json-pointer, task-scheduler, template-engine, ledger, url-router | 2–4 source modules + public API |

The large tier was authored for this run: each is a stub package with a ≥8-scenario
spec, a withheld ≥2-file change, and **hidden** acceptance tests (`acc.py` /
`acc_change.py`) injected only at grading. Every acceptance file was validated
against a reference solution before running (reference passes; shipped golden repo
is stubs only, so the build cannot cheat off the graded tests).

## Pre-registration

- **Model:** `claude-sonnet-4-6`, fixed for the whole run.
- **Trials:** N=3 per (task × arm) for the instruction arms; N=2 for build-pipeline
  (it is ~2–3× the cost/time). Pre-registered before looking at results.
- **Unit of inference:** the **task**. Per (task, arm) we take the **median across
  trials** of the two-stage total cost (build + change), then form **paired arm
  differences across the 6 tasks** within a size and test them with an exact
  **sign test** and an exact **Wilcoxon signed-rank** test.
- **Stopping rule:** run the pre-registered N; no data-dependent stopping.
- **Quality** is read from the **build stage only** (`self_coverage.percent`,
  `mutation.score`); any value uniform across all arms is treated as a saturated
  sensor, not a finding.

## Methodology (concise)

Paired, multi-arm, repeated-trial, two-stage. Each cell (`task × arm × trial ×
stage`) runs in its **own ephemeral git worktree and its own scratch `$HOME`**,
dispatched as a fresh `claude -p --output-format json` (verified
cost/tokens/turns; no session resume, so context cannot leak). **Stage 2** applies
the withheld change seeded from the Stage-1 **files only**. **Acceptance tests are
hidden** during the build and injected only at grading, so each arm must write its
own tests against the prose spec. Cost is read from the native JSON result (the
plugin cost-meter does not fire in nested dispatch). The build-pipeline arm gets a
plugin-enabled `$HOME` per cell so the dev-team plugin loads.

---

## Results — the 3×3 grid

_(filled by `scripts/analyze_tdd_experiment.py` on completion)_

<!-- RESULTS_GRID -->

## Paired statistics

<!-- PAIRED_STATS -->

## What separates (and what doesn't)

<!-- INTERPRETATION -->

## Limitations

- **n = 6 tasks per size** is small; paired tests across 6 pairs cannot reach
  p < 0.03 at best (exact sign/Wilcoxon floor). Treat single-size results as
  directional and the cross-size *pattern* as the real signal.
- **Single model.** The prior work showed the cost winner flips with model; this
  run fixes sonnet, so it says nothing about haiku/opus.
- **Build-pipeline at N=2** has less within-task stability than the instruction
  arms at N=3.
- **Medium tier is folded from the 2026-06-21 sonnet run (N=1/trial)**, not
  re-run; its trial count is lower than small/large. It is the same model, tasks,
  harness, and grading, but the asymmetry is noted.
- **Change-stage quality sensors** are not used (the prior run found a
  uniform-across-arms artifact there — see prior report Limitation 4); quality is
  build-stage only.

## Reproducibility

```bash
pip install coverage pytest
# plugin-enabled HOME for the build-pipeline arm
TPL=/tmp/build-home-tpl; mkdir -p "$TPL/.claude"
cp ~/.claude/settings.json "$TPL/.claude/"; cp -r ~/.claude/plugins "$TPL/.claude/"

# per size, per task: instruction arms @3 trials + build-pipeline @2 trials
python3 scripts/run_tdd_experiment.py --arm test-first --arm test-after \
  --only "<task>" --trials 3 --model claude-sonnet-4-6 --out small.jsonl
python3 scripts/run_tdd_experiment.py --arm build-pipeline \
  --only "<task>" --trials 2 --model claude-sonnet-4-6 \
  --build-home-template /tmp/build-home-tpl --out small_build.jsonl

# analyze
python3 scripts/analyze_tdd_experiment.py \
  --data data/3sizes-small-sonnet-2026-06-22.jsonl \
  --data data/tdd-largetask-sonnet-2026-06-21.json \
  --data data/3sizes-large-sonnet-2026-06-22.jsonl
```

## Recommendation

<!-- RECOMMENDATION -->
