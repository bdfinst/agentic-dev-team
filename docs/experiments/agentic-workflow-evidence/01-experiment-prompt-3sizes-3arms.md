# Experiment Prompt: Build-Pipeline vs. TDD vs. Non-TDD across Small / Medium / Large Tasks

**Type:** Reusable experiment prompt (hand this whole file to Claude to execute)
**Harness:** [`scripts/run_tdd_experiment.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/scripts/run_tdd_experiment.py)
**Design + prior results:** `tdd-vs-test-after-experiment.md`,
`tdd-vs-test-after-consolidated-report.md` (prior campaign; not migrated into this docs set)

---

## Prompt

> Run a controlled experiment comparing three coding workflows across three task
> sizes, then write a consolidated report. Use the existing harness
> `scripts/run_tdd_experiment.py` (do not rebuild it). Work on a feature branch;
> commit data and the report; do not open a PR unless asked.
>
> **Arms (the workflow is the only thing that varies):**
> 1. **build-pipeline** — the real dev-team `/plan`→/`build` pipeline (`--arm build-pipeline`).
> 2. **TDD** — strict test-first RED-GREEN-REFACTOR (`--arm test-first`).
> 3. **non-TDD** — all production code first, tests written at the end (`--arm test-after`).
>
> **Task sizes (≥6 tasks per size, each with a withheld Stage-2 change + hidden
> acceptance tests):**
> - **small** — single-function katas. Reuse: `word-tally, roman, fizzbuzz, rpn,
>   rle, caesar`.
> - **medium** — single-module, multi-function. Reuse: `stats, intervals,
>   timeparse, money, matrix, csvlite`.
> - **large** — **multi-file / multi-module** features (a small package: 2–4
>   source files + a public API), where planning and review can actually pay off.
>   These do not exist yet — **author them first** (see "Authoring large tasks").
>
> **Run the full matrix:** 3 sizes × 3 arms × ≥6 tasks × N trials × 2 stages
> (build + change). Then analyze per size per arm and write the report.

---

## Fixed procedure (follow exactly)

### 0. Preconditions
- `pip install coverage pytest` (sensors need them).
- Build a plugin-enabled HOME template for the build-pipeline arm:
  ```bash
  TPL=/tmp/build-home-tpl; mkdir -p "$TPL/.claude"
  cp ~/.claude/settings.json "$TPL/.claude/"; cp -r ~/.claude/plugins "$TPL/.claude/"
  ```
- Confirm the model id and that nested `claude -p` works (`IS_SANDBOX=1` is set by
  the harness so `--dangerously-skip-permissions` works under root).

### 1. Model
Use one **fixed, capable** model for the whole run and report it (e.g.
`claude-sonnet-4-6`). Do not mix models within a run — the prior experiment
showed the cost winner **flips with model and size**, so the model is a
controlled variable, not a free one.

### 2. Trials & scale
- Target **N = 3 trials** per (task × arm) for instruction arms; **2** for
  build-pipeline (it is ~3–10× the cost/time).
- The unit of inference is the **task**: per task take the median across trials,
  form the paired arm differences, test **across tasks** per size.

### 3. Authoring large tasks (do this before running)
Each large task needs a **multi-file** package so the pipeline's planning/review
has something to bite on. For each:
- `golden-repo.tar.gz` — a stub package: e.g. `pkg/__init__.py` (public API),
  `pkg/core.py`, `pkg/io.py` (empty/stub), plus a README pointing at `spec.md`.
- `spec.md` — a feature spanning ≥2 modules with ≥8 acceptance scenarios.
- `change.md` — a **withheld, behavior-modifying** change that touches ≥2 files.
- `acc.py` / `acc_change.py` — **hidden** acceptance tests (kept out of the
  worktree; injected only at grading via `gradeFiles` / `changeGradeFiles`).
- `evals/experiments/exp-tdd-<name>.json` with the `experiment` block.
- **Validate every acceptance file against a reference solution before running**
  (the prior run did this; never grade with broken tests).

Suggested large tasks: `mini-spreadsheet` (cells + formulas + evaluation),
`json-pointer` (parse + resolve + patch), `task-scheduler` (deps + topo order +
cycle detection), `template-engine` (parse + render + partials),
`ledger` (accounts + postings + balance report), `url-router` (patterns +
match + reverse).

### 4. Execute (sharded — sonnet dispatches run ~5–14 min each)
Run one size at a time. For each size, launch **parallel runners** (cells are
fully isolated) writing to separate JSONL files, then merge. Example for one size:
```bash
SMALL="exp-tdd-word-tally,exp-tdd-roman,exp-tdd-fizzbuzz,exp-tdd-rpn,exp-tdd-rle,exp-tdd-caesar"
# instruction arms together; build-pipeline split out (it is the long pole)
python3 scripts/run_tdd_experiment.py --arm test-first --arm test-after \
  --only "$SMALL" --trials 3 --model claude-sonnet-4-6 \
  --run-root /tmp/run_small_instr --out /tmp/small_instr.jsonl &
python3 scripts/run_tdd_experiment.py --arm build-pipeline \
  --only "$SMALL" --trials 2 --model claude-sonnet-4-6 \
  --build-home-template /tmp/build-home-tpl \
  --run-root /tmp/run_small_build --out /tmp/small_build.jsonl &
```
Shard further by task if a runner lags (give the slowest tasks their own runner).
**Monitor non-destructively** (poll the row count / `pgrep`); never kill the
session's own `claude` process. The harness writes one JSONL row per cell-stage
and flushes per cell.

### 5. Analyze (per size, per arm)
Merge all JSONL (dedupe by `task,arm,trial,stage`, keep last). Report per size:
- **Correctness:** cell pass rate.
- **Cost:** median total `cost_usd` (build + change) per task per arm; arm medians;
  paired arm differences across tasks + a sign/Wilcoxon test.
- **Test quality (build stage only):** `self_coverage.percent`, `mutation.score`.
  Treat any **uniform-across-arms** value as a sensor artifact and exclude it
  (the change-stage sensor had this bug — see report Limitation 4).
- **Turns / contamination:** sanity checks; flag any non-empty `contamination`.

### 6. Report
Write `docs/experiments/<name>-report.md`: methodology delta, a per-size results
table (the 3×3 grid), the paired stats, what separates (or doesn't), honest
limitations (trials, model, sensor caveats), reproducibility commands, and a
recommendation. Commit the report **and** the raw data under
`docs/experiments/agentic-workflow-evidence/data/`.

---

## Guardrails (lessons already paid for — do not relearn)

1. **build-pipeline needs the gate bypassed headlessly.** The arm prompt already
   self-approves the `/plan` gate; without it ~21% of cells stall. If pass rate
   drops, check for "Do you approve this plan?" in the raw output, not the code.
2. **Cost comes from the JSON result**, not the plugin cost-meter (the meter does
   not fire in nested dispatch). The harness reads `--output-format json`.
3. **Hide acceptance tests during the build** (gradeFiles), or every arm just
   makes the given tests pass and the quality signal dies.
4. **Hold the model fixed and report it** — the cost winner flips with model/size.
5. **Small/medium katas saturate the quality sensors** (≈100% cov, 1.0 mutation);
   expect quality to separate, if at all, only on the **large** multi-file tasks.
   That separation is the main reason this run adds the large tier.
6. **Parallelize but isolate** — each cell already gets its own worktree + `$HOME`;
   safe to run many runners concurrently. Watch out for defunct zombies inflating
   `pgrep` counts (harmless).
7. **Pre-register N and the stopping rule**; the task is the unit of inference.

## Expected deliverables
- `evals/experiments/exp-tdd-<large-task>.json` + fixtures for the new large tier.
- Raw data JSONL per size under `docs/experiments/agentic-workflow-evidence/data/`.
- One consolidated report with the 3×3 (size × arm) grid and the verdict.
