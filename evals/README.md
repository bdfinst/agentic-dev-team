# Eval corpus

Fixtures (`fixtures/`) and their expected gradings (`expected/*.json`) for the
review agents and advisory skills. The `/agent-eval` skill dispatches agents
against these fixtures and grades the results; `scripts/eval_grade.py` is the
deterministic, model-free grader that backs CI.

## CI gate (issue #99)

`.github/workflows/agent-eval.yml` runs on every PR that touches
`plugins/dev-team/agents/`, `skills/`, `knowledge/`, or `evals/`:

1. **Structural gate (always, model-free).** `eval_grade.py --check-corpus`
   asserts every `expected/*.json` is valid, declares an agent/skill target,
   and pairs with a fixture; `tests/repo/eval_grader_tests.bats` exercises the
   grader. No tokens, no flakes.
2. **Live gate (opt-in).** Dispatches the agents, records their outputs to
   `actuals.json`, and grades against `baseline.json`, failing the PR on any
   **regression** with a readable diff. It is **OFF by default** and only runs
   when the repo/environment variable `RUN_LIVE_AGENT_EVAL=true` **and**
   `ANTHROPIC_API_KEY` is set — having the key alone is not enough, because the
   eval dispatch requires the Claude Code runner to be wired into the
   "Run agent-eval" step first. When not enabled the live gate is **skipped,
   not failed** (an explicit GitHub notice is emitted); the structural gate
   still runs.

   To activate: wire the Claude Code GitHub Action into the "Run agent-eval"
   step so it runs `/agent-eval` and writes `actuals.json` in the shape below,
   then set `RUN_LIVE_AGENT_EVAL=true`.

### Grader input shape (`actuals.json`)

```json
{
  "<fixture-stem>": {
    "agents": {
      "<agent>": { "status": "fail",
                    "issues": [{ "severity": "error", "message": "..." }],
                    "summary": "..." }
    },
    "skills": {
      "<skill>": { "report": "full advisor report text",
                    "gates": ["A"], "layers": ["unit"] }
    }
  }
}
```

The fixture stem is the `expected/*.json` filename without `.json`
(`fp-global-state.json` → `fp-global-state`).

### Baseline (`baseline.json`)

`baseline.json` lists `fixture::agent` (and `fixture::skill`) pairs known to
pass a green live run. The live gate only blocks on **regressions** — a listed
pair that now fails — so an empty `passing` list never red-lines the gate.

To record/update the baseline:

```bash
# 1. Run a green live eval to produce actuals.json (Claude Code runner).
# 2. Grade with no baseline to see the full pass set:
python3 scripts/eval_grade.py --actuals actuals.json
# 3. Add the passing "fixture::agent" pairs to baseline.json "passing",
#    and set "recorded_at" to the run date.
```
