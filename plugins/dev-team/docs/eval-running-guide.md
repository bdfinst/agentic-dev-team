# Running a full eval of everything

How to run a complete, **clean** accuracy + variance eval across all review
agents. For *how the eval system works and how to keep it current*, see
[`eval-maintenance.md`](eval-maintenance.md). For the architecture, see
[`eval-system.md`](eval-system.md).

## The one rule that matters: do not bias the dispatch

An eval is only valid if the agent produces the verdict it would produce in
production. The fastest way to ruin a run is to leak the answer into the prompt.
Two real contamination modes (both observed, #103):

- **Pre-filling the verdict.** A prompt template like `{"status":"pass", ...}` on
  a pass-fixture tells the agent the answer. Never pre-fill `status`.
- **Leaking an output-format example.** A single `"severity":"warning"` example
  biases the agent's severity choice, which then fails severity-range grading.

**Clean dispatch** = pass the agent **only the fixture** plus, at most, a *neutral
JSON schema* with placeholder enums (`"status":"pass or fail"`,
`"severity":"error, warning, or info"`) — identical for pass and fail fixtures,
no example values, "decide every value yourself." The `/agent-eval` skill enforces
this via its orchestrator constraint #3 ("pass only the fixture file").

## Option 0 — the automated run script (default: resumable full sweep)

```bash
bash scripts/run-full-eval.sh [TRIALS]   # default TRIALS=1; default mode = full sweep
# ...killed / out of tokens? just run it again — it resumes:
bash scripts/run-full-eval.sh
```

**By default this runs the resumable full sweep** (see below): every agent, one at
a time, neutral dispatch, checkpointed. It refreshes the tracked
`evals/baseline.json`, appends the variance trend when `TRIALS>1`, and opens a
single **auto-merge PR** at the end. Needs `claude` + credentials + `gh`. Use
`--agent NAME` to scope to a single agent instead.

### Resumable full sweep (the default) — survives a kill or a token cap

A bare `run-full-eval.sh` runs **all** agents incrementally on one branch,
**committing the baseline after each agent** and tracking progress in a gitignored
checkpoint (`.eval-sweep-progress.json`). If it's interrupted, the completed agents
are already committed and recorded — re-running picks up where it left off and
continues; an interrupted agent is retried. One push, one auto-merge PR at the end.
(`--sweep` is accepted as an explicit alias for this default.)

### Incremental runs — one agent at a time

```bash
bash scripts/run-full-eval.sh 5 --agent security-review   # just this agent, 5 trials
bash scripts/run-full-eval.sh 5 --agent arch-review       # next time, another agent
```

`--agent` makes the run **incremental and safe to repeat**. It scopes the dispatch
to that one agent and grades with `--only`, so the baseline merge **tops up that
agent's pairs and leaves every other agent untouched** (passing added,
present-and-failing removed, un-run pairs kept). Run agents one at a time to spread
cost across sessions — each run accumulates into the same `evals/baseline.json`
and the same variance trend, and opens its own small auto-merge PR.

Why it doesn't clobber: the grader merges rather than overwrites, and `--only`
keeps grading to the scope you ran — so partial coverage is the norm, not a risk.

### The other incremental mode — only what changed

```bash
bash scripts/eval-changed.sh BASE HEAD   # evals only the agents/skills the diff touched
```

This is the pre-push / CI path: it diff-scopes automatically (a change to one agent
evals only that agent; a broad change to `knowledge/` or the corpus falls back to a
full run). Use it to validate a change without re-running everything.

Use Option A/B below when you want manual control or finer per-fixture batching.

## Option A — the native skill (preferred)

```
/agent-eval --trials 5            # all agents × all applicable fixtures, 5 trials
/agent-eval --agent security-review --trials 5   # one agent (budget-friendly)
```

The skill dispatches each fixture to its applicable agents via `/review-agent`
(native invocation, fixture-only context), grades deterministically, computes
pass@k, and — via `scripts/eval_variance.py` — records flap/quarantine and appends
the trend. This is the path that cannot leak format examples.

**Path note:** the skill resolves fixtures at `.claude/evals/fixtures/` (an
*installed* project). In this dev repo the corpus is `evals/` — run it in an
installed test project, or drive the grader/aggregator directly against `evals/`
(Option B).

## Option B — manual neutral dispatch (dev repo / explicit control)

Per agent, per fixture, per trial:

1. Dispatch the agent (e.g. `dev-team:security-review`) with the **neutral**
   prompt above and the fixture path. Capture its JSON verdict.
2. Assemble one **actuals** file per trial — the shape `eval_grade.py` reads:

   ```json
   { "<fixture-stem>": { "agents": { "<agent>": {"status":"...","issues":[{"severity":"...","message":"..."}],"summary":"..."} } } }
   ```

   Record **faithfully** — the issue messages/summary must keep the real wording
   (the grader checks `mustMention`/`mustNotMention` against them).
3. Aggregate the trials:

   ```bash
   python3 scripts/eval_variance.py --trials-dir <dir-of-trial-actuals> \
     --expected-dir evals/expected --append metrics/eval-variance.jsonl
   ```

## Batch for budget — per agent, highest-recall first

A full 3–5-trial run of all ~20 agents is hundreds of model dispatches and will
exceed a small budget. **Run per-agent batches**, recall-critical agents first
(security, arch, domain), at `--trials 5`. The variance trend accumulates across
batches, so you don't need one giant run.

Rough sizing: one agent × its fixtures × 5 trials ≈ 25–40 dispatches. Multiply by
the agent's model tier cost (frontier agents are pricier).

## Reading the results

`eval_variance.py` reports per `fixture::agent`:

- **pass@k = 1.0, no flap** → stable, trustworthy.
- **0 < pass@k < 1 (flap)** → **quarantine**: the pair is unstable; it should
  *inform* the #99 CI gate, not hard-block it. Investigate whether the agent is
  genuinely non-deterministic or the fixture is borderline.
- **pass@k = 0 (stable fail)** → usually a **miscalibrated fixture** (the agent is
  right but the expectation is wrong), not an agent bug. Fix the fixture (see the
  `mustMention`/`mustNotMention` patterns in `eval-maintenance.md`, #198) and
  re-grade against the real actuals.

## Checklist for a clean full run

- [ ] Neutral dispatch (no pre-filled status, no severity example, identical prompt
      for pass and fail fixtures).
- [ ] Faithful actuals (real wording preserved for keyword checks).
- [ ] Per-agent batches, recall-critical first, `--trials 5`.
- [ ] Aggregate with `eval_variance.py --append` so the trend accumulates.
- [ ] Quarantine flaky pairs; fix (don't ignore) stable-fail fixtures.
- [ ] Record cost; stop when the budget cap is hit (coverage degrades gracefully —
      the trend keeps what was collected).
