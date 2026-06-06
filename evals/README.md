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
2. **Live gate (paid, label-gated).** Dispatches the review agents via the
   Claude Code GitHub Action (`anthropics/claude-code-action@v1`), records
   their raw outputs to `actuals.json`, and grades against `baseline.json` —
   failing the PR on any **regression** with a readable diff. It costs tokens,
   so it runs **only when the PR carries the `run-eval` label** (or via a
   manual `workflow_dispatch` with `force_live=true`), and only when
   `ANTHROPIC_API_KEY` is set. Otherwise it is **skipped, not failed** (a
   GitHub notice is emitted); the structural gate still runs. A `concurrency`
   group cancels superseded runs so rapid pushes don't stack paid runs.

   **Note on workflow validation:** `claude-code-action` will *self-skip* (no
   model run) on any PR that adds or modifies this workflow file, because
   GitHub requires the workflow to match the default branch. The live gate
   therefore only exercises the agents once `agent-eval.yml` is merged to the
   default branch.

   The runner is wired (it stages the corpus into `.claude/evals/`, installs
   the `dev-team@bfinster` plugin, and prompts the model to write
   `actuals.json` in the shape below). To record the baseline: add the
   `run-eval` label to a PR (post-merge of this workflow), confirm it produces
   a well-formed `actuals.json`, then capture its passing pairs below.

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
