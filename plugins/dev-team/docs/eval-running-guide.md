# Running a full eval of everything

This guide explains how to run a complete, **clean** accuracy and variance eval across all review
agents. For *how the eval system works and how to keep it current*, see
[`eval-maintenance.md`](eval-maintenance.md). For the architecture, see
[`eval-system.md`](eval-system.md).

## The one rule that matters: do not bias the dispatch

An eval is valid only if the agent produces the verdict it would produce in
production. The fastest way to ruin a run is to leak the answer into the prompt.
Two real contamination modes exist (both observed, #103):

- **Pre-filling the verdict.** A prompt template like `{"status":"pass", ...}` on
  a pass-fixture tells the agent the answer. Never pre-fill `status`.
- **Leaking an output-format example.** A single `"severity":"warning"` example
  biases the agent's severity choice. That bias then fails severity-range grading.

**Clean dispatch** means you pass the agent **only the fixture** plus, at most, a *neutral
JSON schema* with placeholder enums (`"status":"pass or fail"`,
`"severity":"error, warning, or info"`). The schema is identical for pass and fail fixtures.
It has no example values and says "decide every value yourself." The `/agent-eval` skill enforces
this through its orchestrator constraint #3 ("pass only the fixture file").

## Option 0 — the automated run script (default: resumable full sweep)

```bash
bash scripts/run-full-eval.sh [TRIALS]   # default TRIALS=1; default mode = full sweep
# ...killed / out of tokens? run it again — it resumes:
bash scripts/run-full-eval.sh
```

**By default this runs the resumable full sweep** (see below). It runs every agent, one at
a time, with neutral dispatch and checkpoints. It refreshes the tracked
`evals/baseline.json`, appends the variance trend when `TRIALS>1`, and opens a
single **auto-merge PR** at the end. It needs `claude`, credentials, and `gh`. Use
`--agent NAME` to scope the run to a single agent instead.

### Resumable full sweep (the default) — survives a kill or a token cap

A bare `run-full-eval.sh` runs **all** agents incrementally on one branch.
It **commits the baseline after each agent** and tracks progress in a gitignored
checkpoint (`.eval-sweep-progress.json`). If the run is interrupted, the completed agents
are already committed and recorded. Re-running picks up where it left off, and
the script retries an interrupted agent. The script makes one push and opens one auto-merge PR at the end.
(`--sweep` is an explicit alias for this default.)

### Incremental runs — one agent at a time

```bash
bash scripts/run-full-eval.sh 5 --agent security-review   # just this agent, 5 trials
bash scripts/run-full-eval.sh 5 --agent arch-review       # next time, another agent
```

`--agent` makes the run **incremental and safe to repeat**. It scopes the dispatch
to that one agent and grades with `--only`. The baseline merge then **tops up that
agent's pairs and leaves every other agent untouched** (passing added,
present-and-failing removed, un-run pairs kept). Run agents one at a time to spread
cost across sessions. Each run accumulates into the same `evals/baseline.json`
and the same variance trend, and opens its own small auto-merge PR.

Why it does not clobber: the grader merges rather than overwrites, and `--only`
keeps grading to the scope you ran. Partial coverage is the norm, not a risk.

### The other incremental mode — only what changed

```bash
bash scripts/eval-changed.sh BASE HEAD   # evals only the agents/skills the diff touched
```

This is the pre-push and CI path. It diff-scopes automatically. A change to one agent
evals only that agent. A broad change to `knowledge/` or the corpus falls back to a
full run. Use it to validate a change without re-running everything.

Use Option A/B below when you want manual control or finer per-fixture batching.

## Option A — the native skill (preferred)

```
/agent-eval --trials 5            # all agents × all applicable fixtures, 5 trials
/agent-eval --agent security-review --trials 5   # one agent (budget-friendly)
```

The skill dispatches each fixture to its applicable agents through `/review-agent`
(native invocation, fixture-only context). It grades deterministically and computes
pass@k. Through `scripts/eval_variance.py`, it records flap and quarantine status and appends
the trend. This path cannot leak format examples.

**Path note:** the skill resolves fixtures at `.claude/evals/fixtures/` (an
*installed* project). In this dev repo the corpus is `evals/`. Run the skill in an
installed test project, or drive the grader and aggregator directly against `evals/`
(Option B).

## Option B — manual neutral dispatch (dev repo / explicit control)

Per agent, per fixture, per trial:

1. Dispatch the agent (e.g. `dev-team:security-review`) with the **neutral**
   prompt above and the fixture path. Capture its JSON verdict.
2. Assemble one **actuals** file per trial — the shape `eval_grade.py` reads:

   ```json
   { "<fixture-stem>": { "agents": { "<agent>": {"status":"...","issues":[{"severity":"...","message":"..."}],"summary":"..."} } } }
   ```

   Record **faithfully**. The issue messages and summary must keep the real wording.
   The grader checks `mustMention` and `mustNotMention` against them.
3. Aggregate the trials:

   ```bash
   python3 scripts/eval_variance.py --trials-dir <dir-of-trial-actuals> \
     --expected-dir evals/expected --append .claude/metrics/eval-variance.jsonl
   ```

## Batch for budget — per agent, highest-recall first

A full 3–5-trial run of all ~20 agents is hundreds of model dispatches and
exceeds a small budget. **Run per-agent batches**, recall-critical agents first
(security, arch, domain), at `--trials 5`. The variance trend accumulates across
batches, so you do not need one giant run.

Rough sizing: one agent × its fixtures × 5 trials ≈ 25–40 dispatches. Multiply by
the agent's model tier cost. Frontier agents cost more.

## Reading the results

`eval_variance.py` reports per `fixture::agent`:

- **pass@k = 1.0, no flap** → stable, trustworthy.
- **0 < pass@k < 1 (flap)** → **quarantine**. The pair is unstable. It should
  *inform* the #99 CI gate, not hard-block it. Investigate whether the agent is
  genuinely non-deterministic or the fixture is borderline.
- **pass@k = 0 (stable fail)** → usually a **miscalibrated fixture** (the agent is
  right but the expectation is wrong), not an agent bug. Fix the fixture and
  re-grade against the real actuals. See the
  `mustMention` and `mustNotMention` patterns in `eval-maintenance.md` (#198).

## Checklist for a clean full run

- [ ] Neutral dispatch (no pre-filled status, no severity example, identical prompt
      for pass and fail fixtures).
- [ ] Faithful actuals (real wording preserved for keyword checks).
- [ ] Per-agent batches, recall-critical first, `--trials 5`.
- [ ] Aggregate with `eval_variance.py --append` so the trend accumulates.
- [ ] Quarantine flaky pairs. Fix (do not ignore) stable-fail fixtures.
- [ ] Record cost. Stop when the budget cap is hit. Coverage degrades gracefully,
      and the trend keeps what you collected.
