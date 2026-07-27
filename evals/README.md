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
2. **Live gate (paid, label-gated).** Dispatches the review agents via the bare
   `claude` CLI (`@anthropic-ai/claude-code`), records their raw outputs to
   `actuals.json`, and grades against `baseline.json` — failing the PR on any
   **regression** with a readable diff. It costs tokens, so it runs **only when
   the PR carries the `run-eval` label** (or via a manual `workflow_dispatch`
   with `force_live=true`), and only when `ANTHROPIC_API_KEY` is set. Otherwise
   it is **skipped, not failed** (a GitHub notice is emitted); the structural
   gate still runs. A `concurrency` group cancels superseded runs so rapid
   pushes don't stack paid runs.

   > **Why the bare CLI, not `anthropics/claude-code-action`?** The action wraps
   > the CLI in a Bun runtime that crashes at launch in CI ("directory mismatch
   > for tsconfig.json", fd 4) before any API call — upstream
   > [#1205](https://github.com/anthropics/claude-code-action/issues/1205) /
   > [#1295](https://github.com/anthropics/claude-code-action/issues/1295), not
   > fixable by version/SHA pinning. The live gate dispatches the agents
   > directly with `claude -p`, mirroring the integration tier.

   **Diff-scoped runs.** The live gate runs only the agents/skills the PR
   changed (derived from the diff and threaded into both the runner prompt and
   `eval_grade.py --only`). A broad change — `knowledge/`, the corpus, the
   grader, or the workflow — falls back to a full run, since one knowledge file
   can feed many agents. This is the main per-run cost lever.

   The runner is wired (it stages the corpus into `.claude/evals/`, installs the
   `claude` CLI and the `dev-team@bfinster` plugin, and prompts the model to
   write `actuals.json` in the shape below). Unlike the GitHub Action, the bare
   CLI has no self-skip on PRs that modify this workflow, so the gate can be
   exercised on the labeling PR itself. To record the baseline: add the
   `run-eval` label to a PR, confirm it produces a well-formed `actuals.json`,
   then capture its passing pairs below.

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

The **fingerprint replay cache** (below, #311) is the other half of that
calculus: it removes the proximate reason every run was full-cost, so a
cost-budgeted default-on posture becomes affordable once the metering exists.

## Grader registry (issue #309)

Grading is dispatched through a pluggable registry in `scripts/eval_graders/`
rather than a monolith. Each grader is a module exposing
`grade(spec, actual) -> list[str]` (empty list == PASS) registered in
`eval_graders/__init__.py`:

| grader | default for block | grades |
| --- | --- | --- |
| `verdict` | `agents` | a review agent's status / issue counts / severities / keywords |
| `skill_gate` | `skills` | an advisory skill's gates + pyramid layers + report keywords |
| `integration` | `integration` | recorded test-command exit codes (#313) |

An expected entry may set `"grader": "<name>"` to override its block default.
`--check-corpus` rejects an unknown grader value. Adding a fixture genre is one
module + one `REGISTRY` entry — no edits to existing graders.

## Dispatch mode (issue #310)

`/agent-eval` dispatches each pair through a **fresh `claude -p` subprocess by
default**, so the agent/skill definition is re-read from disk every run and a
just-edited definition is graded immediately. `--in-session` is an opt-in fast
path that reuses the already-loaded definitions for cheap re-grades when nothing
has been edited. Missing `claude` on `PATH` is a hard error in default mode —
never a silent fallback to the (possibly stale) in-session path.

## Fingerprint replay cache (issue #311)

`scripts/eval_cache.py` makes the live gate economical. Before dispatching a
`fixture::target` pair it computes a SHA-256 over the target's definition, the
**transitive closure** of files it reaches (`knowledge/*.md`, `skills/*`), the
fixture file(s), the expected JSON, and the grader version. An unchanged SHA
with a stored PASS replays from `evals/.eval-cache.json` at **zero token cost**;
any changed input busts the cache and forces a live dispatch.

```bash
python3 scripts/eval_cache.py --fingerprint "ar-layer-violation::arch-review"
python3 scripts/eval_cache.py --plan --replay-out replay.json   # hits vs misses
python3 scripts/eval_cache.py --store --actuals actuals.json    # memoize passes
```

The cache file is gitignored. Corruption is silently ignored (degrades to a
full dispatch, never errors). CI restores the per-branch cache before dispatch,
merges replayed hits into `actuals.json`, grades, stores new passes, and uploads
the cache as a workflow artifact.

## Citation drift lint (issue #312)

`scripts/citation_lint.py` is a preventive guard against reviewer agents
enforcing stale thresholds. An agent declares its canonical sources in a
`cites:` frontmatter list; every numeric threshold the agent states on an
RFC-2119 line (MUST/SHOULD/SHALL/REQUIRED/NEVER/ALWAYS) must appear in a cited
skill/knowledge file, else it is flagged as drift with token + line number. It
runs in `/agent-audit` and in CI. **Phase 1 is advisory** (always exit 0) to
collect signal before hardening. Code fences and blockquotes are excluded.

## Calibration provenance (issue #1466)

An expected fixture's `min`/`max` tolerance windows (`issueCount`,
`severities.<sev>`) have no way to carry *why* those specific bounds were
chosen — JSON can't carry comments. A future "tidy up the ranges" pass could
narrow or widen a fixture's bounds to match a neighboring fixture's shape
without realizing the original bound was tuned against that fixture's own
measured behavior, silently weakening the eval's discriminating power with
nothing to catch it.

**Convention: an optional `_calibration` field**, nested inside the specific
`agents.<name>` / `skills.<name>` entry — sibling to `issueCount` /
`severities` — not at the fixture's top level. This keeps the note next to
the bounds it explains and scales to a (currently nonexistent, but possible)
multi-target fixture where different targets' bounds have different
provenance.

Shape:

```json
"_calibration": {
  "source": "measured" | "estimated-by-analogy",
  "note": "<one-line rationale>"
}
```

- `source: "measured"` — the bound was derived from an actual calibration run
  against the target agent/skill's real output on this fixture.
- `source: "estimated-by-analogy"` — the bound was guessed by analogy to a
  neighboring fixture's shape, not independently measured.
- `note` — one line of free-text rationale (which run, or which neighbor it
  was modeled on).

`eval_grade.py --check-corpus` explicitly recognizes and shape-checks
`_calibration` when present (unknown `source` values fail the corpus gate),
but the field is **purely informational** — the grader never reads it when
scoring an actual run, so its presence or absence never changes pass/fail.

**Required for every NEW fixture going forward** that declares a `min`/`max`
tolerance window. **Do not retrofit** the ~140 existing `evals/expected/*.json`
fixtures — that is out of scope and would be pure churn with no discovered
provenance to record.

Worked example:

```json
{
  "fixture": "test-internal-collaborator-mock.test",
  "applicableAgents": ["test-smell-review"],
  "agents": {
    "test-smell-review": {
      "expectedStatus": "warn",
      "issueCount": { "min": 1, "max": 3 },
      "severities": { "warning": { "min": 1, "max": 2 } },
      "mustMention": ["same component", "component-test-patterns"],
      "mustNotMention": [],
      "_calibration": {
        "source": "measured",
        "note": "Bounds observed from 3 live agent-eval runs against test-smell-review at HEAD (2026-07-27)"
      }
    }
  }
}
```

## Integration tier — golden repo (issue #313)

The unit graders score a single agent's output in isolation. The integration
tier asks the validation question instead: *does a plan from the orchestrator
yield code that compiles and whose tests pass?* An integration fixture's
expected JSON carries an `integration` block naming a frozen `spec`, a
`goldenRepo` tarball, and a non-empty `testCommands` list:

```json
{
  "integration": {
    "orchestrator": {
      "grader": "integration",
      "spec": "spec.md",
      "goldenRepo": "golden-repo.tar.gz",
      "testCommands": ["python3 test_string_calc.py"]
    }
  }
}
```

`scripts/run_integration_eval.py` builds an **ephemeral git worktree** from the
tarball, dispatches the orchestrator against the spec, runs the test commands,
records exit codes, and tears the worktree down unconditionally. The
`integration` grader passes only when every command exits 0. The tier is
**opt-in** (`run-integration` label / `force_integration`), never in the default
PR suite, and depends on the grader registry (#309) and the replay cache (#311).
Use `--skip-dispatch` to exercise the harness without a model (commands run
against the golden repo as-is). The first shipped fixture is
`int-string-calculator` (the String Calculator kata: plan → implement → review).

See [ADR 0007](../docs/adr/0007-eval-confidence-pyramid-tier-vocabulary.md) for
the tier vocabulary (unit → integration → acceptance).
