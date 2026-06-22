# TDD vs. test-after experiment fixtures

Fixtures for the validation experiment in
[`docs/experiments/tdd-vs-test-after-experiment.md`](../../docs/experiments/tdd-vs-test-after-experiment.md).
Run with [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py).

These intentionally live **outside** `evals/expected/` so the unit grader
(`eval_grade.py`, which globs `evals/expected/*.json`) and the integration runner
(which keys on an `integration` block) never pick them up. The experiment runner
keys on an `experiment` block instead.

## Layout

```
evals/experiments/exp-tdd-<task>.json     # expected/manifest (the experiment block)
evals/fixtures/exp-tdd-<task>/
├── golden-repo.tar.gz                     # frozen Stage-1 starting point
├── spec.md                                # Stage 1: the feature to build
└── change.md                              # Stage 2: the WITHHELD follow-up change
```

`exp-tdd-template.json` is a copy-me template; the runner skips it by name.

## The `experiment` block

```json
{
  "experiment": {
    "goldenRepo": "golden-repo.tar.gz",
    "spec": "spec.md",
    "change": "change.md",
    "testCommands": ["python3 test_feature.py"],
    "changeTestCommands": ["python3 test_feature.py", "python3 test_change.py"]
  }
}
```

- `testCommands` grade Stage 1 (build); `changeTestCommands` grade Stage 2 (the
  change), and should include the Stage-1 commands so a regression fails the cell.
- Each cell (`task × arm × trial × stage`) runs in its own ephemeral worktree and
  its own scratch `$HOME`, so cost meters and `memory/` never collide. Stage 2 is
  a **fresh** dispatch seeded with the Stage-1 *files* only — no shared context.

## Sizing a task (so the data can discriminate)

Per the experiment doc, a task must be **large enough to diverge** yet **fit one
context window**:

- ≥ 5–8 acceptance scenarios (multiple behaviors, not one function).
- A `change.md` that **modifies existing behavior**, not just appends — that is
  what stresses the suite as a safety net and reveals changeability.
- Small enough that a competent dev finishes in ~1–3 hours (no summarization).

## Running

```bash
# Harness self-test (no model): proves isolation + plumbing.
python3 scripts/run_tdd_experiment.py --skip-dispatch --trials 1

# Real campaign: both arms, repeated trials (set N from a pilot's variance).
python3 scripts/run_tdd_experiment.py --trials 6 --model claude-sonnet-4-6
```

Results append to `metrics/tdd-experiment.jsonl` (one row per cell-stage) with
`cost`, `rework`, and `contamination` fields. Aggregate **per task** (the unit of
inference) **per arm**, then apply the pre-registered decision rule in the doc.
```
