# Eval corpus

Fixtures (`fixtures/`) and their expected gradings (`expected/*.json`) for the
review agents and advisory skills. The `/agent-eval` skill dispatches agents
against these fixtures and grades the results; `scripts/eval_grade.py` is the
deterministic, model-free grader that backs CI.

## CI gate (issue #99)

`.github/workflows/agent-eval.yml` triggers on every PR that touches
`plugins/dev-team/agents/`, `skills/`, `knowledge/`, or `evals/`. Triggering
runs the **structural gate**; the **live gate is opt-in** and does **not**
enforce on every PR (see below):

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

   **Diff-scoped runs.** The live gate runs only the agents/skills the PR
   changed (derived from the diff and threaded into both the runner prompt and
   `eval_grade.py --only`). A broad change — `knowledge/`, the corpus, the
   grader, or the workflow — falls back to a full run, since one knowledge file
   can feed many agents. This is the main per-run cost lever.

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

To record/update the baseline from a **real** run:

```bash
# 1. Trigger a green live eval to produce actuals.json:
#    add the `run-eval` label to a PR (post-merge of agent-eval.yml), or
#    dispatch the workflow with force_live=true. Both require ANTHROPIC_API_KEY.
# 2. Grade the run and write the baseline in one step — this stamps
#    provenance="measured" and recorded_at=the run time, and MERGES (passing
#    pairs added, tested-but-failing removed, untested pairs kept):
python3 scripts/eval_grade.py --actuals actuals.json --write-baseline evals/baseline.json
```

### Provenance (issue #133)

`baseline.json` carries a `provenance` field:

- `hand-authored` — the `passing` set was asserted by hand, **not** measured by
  a live run. `recorded_at` is then the authoring date, not a run timestamp.
- `measured` — written by `--write-baseline` from grading a real `actuals.json`.
  `recorded_at` is the actual run time.

The seed baseline ships as `hand-authored`. Recording a `measured` baseline
requires the paid `run-eval` path above, so it is done post-merge rather than in
this repo's hermetic CI.

### Opt-in posture & cost (issues #133, #134)

The live gate is **intentionally opt-in** (the `run-eval` label / `force_live`
dispatch) to avoid uncontrolled API spend on every PR. This is a deliberate
cost-control decision, **not** a defect: nothing in shipped prose should claim
the live gate auto-enforces on every PR. A cost-budgeted default-on run will
only be reconsidered **after** #134 (runtime cost metering) can produce a
per-run live-eval cost estimate; until that estimate exists, the gate stays
opt-in and no default-on change is made.
