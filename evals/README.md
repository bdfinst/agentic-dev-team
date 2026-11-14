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
   and pairs with a fixture; `tests/repo/test_eval_grader.py` exercises the
   grader. `scripts/eval_fixture_coverage.py` checks every review agent's
   fixture, hard and clean counts (see "Hard and clean fixtures"). No tokens,
   no flakes.
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
| `finding_ids` | none | planted finding IDs matched by keyword (and optional severity) in a critic's finding lists, plus an optional verdict |
| `dispatch_set` | none | the agents a coordinator dispatched, read from the transcript, plus an optional verdict |
| `tests_pass` | none | recorded exit codes of the fixture's `testCommands` after a write-capable agent's trial |
| `rubric` | none | a recorded rubric judgement: every rubric criterion and `rubricPoints` entry marked met |

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

An agent entry may also declare `expectedFindings`, a list of
`{"category", "severity"}` pairs (#2283). The grader requires the set of
`(category, severity)` pairs in the agent's `issues[]` to equal the declared
set exactly. Use it where `category` is a stable rule id, as for `sql-review`;
`"expectedFindings": []` asserts the agent reports no categorized issue.

## Hard and clean fixtures

Every review agent (`plugins/dev-team/agents/*-review.md`) needs at least 5
fixtures, at least 2 of them hard and at least 1 clean.

- **Clean**: the agent's `expectedStatus` is `pass`, or `skip` when the
  agent's own Skip rule covers the target. The fixture has no expected
  finding, so any finding is a false positive. Make the fixture clean
  for that agent's lens: a clean naming fixture has no magic number and no
  concept named two ways. Whether the agent's Skip rule really covers a
  `skip` fixture is a reviewer judgment: the grader and the coverage gate
  cannot check it.
- **Hard**: the agent's entry carries a `hard` marker. A weaker model tier
  plausibly misses the expected verdict. `reason` is `subtle-defect` (one
  defect hidden in otherwise correct code), `distractor` (code that looks like
  a defect but is not), or `long-file` (the defect sits in a long file).

```json
"hard": {
  "reason": "distractor",
  "note": "sort() runs only on spread copies, so no input array is mutated"
}
```

`eval_grade.py --check-corpus` rejects an unknown `reason` or an empty `note`.
`scripts/eval_fixture_coverage.py` prints the per-agent counts and exits 1
when an agent is below a minimum, or 2 when a directory is missing or an
expected file is malformed (invalid JSON, not an object, or `agents` not an
object), whether or not it has a fixture; `tests/repo/test_eval_fixture_coverage.py`
runs it in the pre-push gate.

Keep the verdict out of the fixture: a header comment such as `// PASS:` or
`// FAIL:` tells the agent the answer.

## Convention: executable claims (issue #1629)

**Any fixture line or `_calibration` note that asserts concrete runtime
behavior must be verified by *running* it at authoring time**, with the probe
and its observed output recorded next to the claim.

"Concrete runtime behavior" means a checkable statement about what code
actually does: *"X throws when unbound"*, *"Y mutates its receiver"*, *"Z
returns a new array"*, *"this call is O(n²)"*. It does not mean a design
opinion or a naming judgment — those are what the reviewer is for.

### Why this exists

In PR #1619, a negative-control fixture asserted that
`Intl.NumberFormat.prototype.format` loses its receiver when called unbound.
The claim was wrong, so the fixture didn't test what it said it tested — and
nothing caught it until an opus-tier `correctness-review` adjudicated it
**two rounds later**, which then cost another round to verify that the
replacement (`RegExp.prototype.test`) was itself correct per ECMA-262.

Every step of that was avoidable. The claim was checkable by execution in
about one second — and executing it shows the situation is not even the one
the fixture described (verified on Node 22.22.2, 2026-07-31):

```console
$ node -e 'Intl.NumberFormat.prototype.format'
TypeError: Method UnwrapNumberFormat called on incompatible receiver undefined
```

`format` is an **accessor**, not a data property (`Object.getOwnPropertyDescriptor(Intl.NumberFormat.prototype, "format").get` is a
function). Merely *reading* it off the prototype throws, because the getter
runs with `this === undefined`. So the method can never be extracted from the
prototype to be "called unbound" in the first place. Extracted from an
*instance*, it works fine unbound — the getter returns an already-bound
closure:

```console
$ node -e 'const f = new Intl.NumberFormat("en-US").format; console.log(f(1234.5))'
1,234.5
```

This example is itself the convention in action: the first draft of this
section asserted that the bare prototype access returns `1`. Running the
probe disproved it in one second, before any reviewer saw it.

The panel should be reviewing an **evidenced** claim, not adjudicating an
unevidenced one. This is the `ai-provenance-review` lens's own
"human-verification evidence" principle applied to this plugin's fixtures:
an AI-authored assertion about runtime behavior carries verification debt
until someone actually ran it.

### How to record the evidence

Put the probe and its output in the fixture's `_calibration.note`, or in a
sibling comment in the fixture file itself when the fixture's format allows
comments:

```json
"_calibration": {
  "source": "measured",
  "note": "Negative control verified by execution: `node -e 'const t = RegExp.prototype.test; try { t(\"x\") } catch (e) { console.log(e.constructor.name) }'` -> TypeError (ECMA-262 22.2.6.16 requires an Object receiver). 2026-07-31."
}
```

### Ordering: run the deterministic checks *before* the first panel

`repo_invariants.py` and the language linters already run inside
`/code-review` step 2b. When authoring fixtures or agent files, run them at
**edit time** instead — same commands, earlier, before any panel dispatches:

```bash
python3 plugins/dev-team/skills/code-review/scripts/repo_invariants.py --files <the files you touched>
```

That pre-pass mechanically enforces the conventions this repo has already
paid for rediscovering: `_calibration` blocks on new bounded fixtures,
`mustNotMention` terms that actually appear in their paired fixture, and
`Scope:`-glob/Skip-prose extension agreement. Add `--all` to triage the
pre-existing backlog these conventions deliberately do not retrofit.

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

## Model and effort A/B harness

`scripts/model_effort_ab.py` compares an agent's frontmatter `model:` and
`effort:` (the baseline arm) with a candidate. Each trial runs through
`claude -p` against a fresh copy of a fixture. The agent's grader, named in
[`evals/model-effort/graders.json`](model-effort/graders.json), scores the trial
against `evals/expected`. The runs are paid API calls.

```bash
python3 scripts/model_effort_ab.py security-review --model haiku --effort medium
```

The harness prints the resolved configuration and a cost estimate, then asks
for approval before it starts the first trial. Trials alternate baseline,
candidate, baseline, and so on, so a broken candidate fails on its first trial.

### Flags

| Flag | Default | Meaning |
| --- | --- | --- |
| `agent` (positional) | none | Agent name, as in `plugins/dev-team/agents/<agent>.md`. Omit it with `--batch`. |
| `--stress` | off | Run the [stress matrix](#stress-matrix): the frontmatter tier, one step down and one step up, with a verdict in the artifact. Cannot be combined with `--model` or `--effort`. |
| `--axis` | `model` | The ladder a `--stress` step moves on: `model` or `effort`. |
| `--batch` | none | `haiku`, `sonnet` or `opus`: a `--stress` run for every agent at that frontmatter tier, approved once. See [Stress batch](#stress-batch). |
| `--model` | frontmatter `model:` | Candidate model. |
| `--effort` | frontmatter `effort:` | Candidate effort level. |
| `--fixtures` | every `evals/expected` entry that names the agent and has a matching fixture in `evals/fixtures` | Comma-separated fixture stems. |
| `--trials` | 10 for `security-review`, `correctness-review`, `architect`, `security-engineer` and rubric-judged agents; otherwise 5 | Trials per arm per fixture. Must be a whole number of 1 or more. |
| `--trial-timeout` | 600 | Seconds before a trial is killed and recorded as `timeout`. |
| `--max-cost` | none | Dollar limit on the estimate and on the charged cost, described in [Spend limit](#spend-limit). |
| `--yes` | off | Skip the confirmation prompt. |
| `--allow-unjailed-checks` | off | Run a fixture's `testCommands` without a jail when no working `sandbox-exec` or `bwrap` is found. Use only on a disposable machine. |
| `--claude-bin` | `claude` | The `claude` executable to run. |
| `--runs-dir` | `evals/model-effort/runs` | Directory the artifact is written to. |

The candidate must differ from the frontmatter in `--model` or `--effort`. The
harness refuses a candidate that ends up equal to the baseline, including a
partial override such as `--model haiku` on an agent that already uses `haiku`.

### Stress matrix

`--stress` runs three arms instead of a baseline and a candidate: the
frontmatter tier (`baseline`), one step down (`step-down`) and one step up
(`step-up`). On the `model` axis a step moves one rung on haiku, sonnet, opus at
the same effort. Where no model rung is left (down from haiku, up from opus) the
step moves effort one level instead (`low`, `medium`, `high`, `xhigh`, `max`). On
the `effort` axis a step moves effort one level at the same model. Where no
effort level is left (down from `low`, up from `max`) the step moves one model
rung instead. A direction with no rung on either ladder has no arm, and the
verdict says so. The run ID names the frontmatter tier.

```bash
python3 scripts/model_effort_ab.py naming-review --stress
```

The artifact's `verdict` is `downgrade`, `upgrade` or `keep`, with its reason.
An expected finding is a fixture whose expected entry is not clean; recall is the
passing trials over all trials on those fixtures.

- **Downgrade** to the step-down tier when, over all its trials, its recall is at
  least the current tier's, its clean-fixture false positives are no more than
  the current tier's, and every trial produced output the grader could judge. A
  parse failure, timeout, CLI error, tool violation or judge error blocks it.
- **Upgrade** to the step-up tier when it passes some expected finding in at
  least half its trials that the current tier misses in every trial, its
  clean-fixture false positives are no more than the current tier's, and every
  one of its trials produced output the grader could judge. A failed check is
  named in the reason. An upgrade wins over a downgrade that also passes.
- **Keep** otherwise, with the failed checks as the reason. A run also keeps when
  it is incomplete, when `tier_change_eligible` is `false` (rubric-judged evidence
  needs 10 graded trials per arm per fixture), or when the agent is
  `correctness-review`, whose results are excluded from evidence while its known
  recall gap is unfixed.

### Stress batch

`--batch <tier>` runs `--stress` for every agent whose frontmatter `model:` is
at that tier. It plans every agent first and lists each one it cannot run
(no fixture, an unsandboxed write-capable agent, a judge below the required
tier, excluded results) with the reason. It prints each agent's configuration
and estimate, then one combined estimate with the rubric judge included, and
asks for approval once. The agents then run one after another, each writing its
own artifact, and the batch stops at the first run that does not complete.
`--max-cost` bounds the combined estimate and the charged cost of the whole
batch: each agent's run gets what is left of it, and once nothing is left the
batch starts no further agent and prints `spend limit reached; not run:` with
the agents it skipped. `--batch` cannot be combined with an agent name, `--model`, `--effort` or
`--fixtures`.

```bash
python3 scripts/model_effort_ab.py --batch haiku
```

Without `--yes` and a terminal, the batch prints the estimates and refuses to
start, so the command doubles as a cost preview.

A batch exits 0 when every agent's run completed, 1 when it was declined,
stopped after a run that did not complete, or reached the spend limit before an
agent, and 2 when no agent at the tier can
run or the combined estimate is above `--max-cost`.

### Inputs are frozen when the run is planned

When the harness plans a run, it copies the fixtures to run, their
`evals/expected` entries and the plugin `knowledge/` directory into one private
temp directory. Every trial stages its fixture from that copy, the `claude`
process reads knowledge from it (`--add-dir`), and grading reads the expected
entry from it. Editing a fixture, an expected entry or a knowledge file after the
run is planned does not change the trials that follow. The `claude` process gets
only the `knowledge` copy, never the expected entries. The harness removes the
copy when the run ends, however it ends. The agent file is read once, at planning, and so are the grader and the
environment-scrub scripts the trials use.
The artifact's `knowledge_dir` names the source directory. Error text in the
artifact shows the copy as `<snapshot>`.

### Approval

Without `--yes`, the harness prompts `Proceed? [y/N]` on a terminal and
runs only on `y` or `yes`. When stdin is not a terminal, it refuses to start
unless you pass `--yes`.

### Spend limit

`--max-cost` applies twice:

- **At start.** The harness refuses to run when the estimate is above the limit.
  For a rubric-graded agent the estimate includes the judge.
- **During the run.** The harness stops after the first trial that takes the charged
  cost above the limit. The charged cost is the reported cost of each trial and of
  each rubric judgement (a failed judgement included), plus the per-trial or
  per-judgement estimate for each one whose `claude` output reports no cost.

The summary prints each arm's cost and the total as `cost X + judge Y, estimated
A + judge B` when a judge ran. The judge estimates add up to the figure the
configuration echo printed before the run, and the artifact records the same
numbers.

The estimate is a rough heuristic. The real cost can be several times higher or
lower: in the one real run, the estimate was 4.6 to 13.6 times the reported cost.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | The run completed and the artifact was written. |
| 1 | The run was declined, stopped early, or a signal arrived while the finished run was being saved (the artifact is still written), or the artifact could not be written. When the write fails, the artifact JSON goes to stdout so the paid results survive. A run interrupted before its first trial writes no artifact and exits 1. |
| 2 | Usage error or refusal before the run. For an invalid argument, an unknown agent or fixture, an agent file that cannot be read or has no valid frontmatter (no `---` block at the top, invalid YAML, or a block that is not a key: value mapping), a missing, blank or invalid `model:` or `effort:` in the agent's frontmatter, identical arms, a write-capable agent `graders.json` does not sandbox, a fixture whose grader does not match the agent's, a `protectedPaths` entry that is absolute or uses `..`, a `tests-pass` run with no working jail and no `--allow-unjailed-checks`, a rubric judge below the required tier, or an unpriced model, the harness prints no configuration and no estimate. For an estimate above `--max-cost`, the harness prints the configuration and the estimate first. No trial runs and no artifact is written. |

Messages go to stderr.

### Stop reasons

A run that stops early still writes an artifact with the completed trials. The
artifact records the reason in `abort_reason`:

| `abort_reason` | Cause |
| --- | --- |
| `max-cost` | The charged cost went above `--max-cost`. |
| `infra-failure` | An arm's first trial failed in the infrastructure, or three consecutive trials did. |
| `interrupt` | Ctrl-C, SIGTERM or SIGHUP. |
| `harness-error` | An unexpected error in the harness. |

A stopped run cannot resume. A rerun starts over.

Ctrl-C, SIGTERM and SIGHUP are held from the first trial until the artifact is
saved, so none of them can drop a completed trial or a half-written artifact. A
signal that arrives while a trial's `claude` process runs kills that process group
and drops that trial. A signal that arrives while the harness grades, records or
saves is acted on at the next safe point: the run starts no further trial and
keeps every completed one. A signal that arrives after the last trial leaves the
run `complete`; the harness saves it and then exits 1. A SIGHUP that the process
ignores, as under `nohup`, does not stop the run. While a trial runs, the
harness notices a signal within 0.1 s. A signal before the first trial starts
stops the run with nothing run or spent.

### Artifact

Each run writes `evals/model-effort/runs/<run-id>.json`. The harness writes the
artifact only when at least one trial started. A run interrupted before its first
trial writes no artifact and exits 1. The key fields:

| Field | Meaning |
| --- | --- |
| `status` | `complete`, or `incomplete` when `abort_reason` is set. |
| `abort_reason` | A stop reason from the table above, or `null`. |
| `arms[].trials_per_fixture` | Trials planned per fixture (the `--trials` value). To count the trials that ran, count `fixtures[].trials`. |
| `grader` | The agent's grader from `graders.json`: `expected-findings`, `tests-pass`, `dispatch-set` or `rubric`. |
| `judge` | For `rubric`: the pinned judge `model`, `effort`, `rubric` path and `criteria`; otherwise `null`. |
| `tier_change_eligible` | `true` when every arm has at least one graded trial (`pass` or `graded_fail`) on every planned fixture and, for `rubric`, at least 10. Timeouts, CLI errors, tool violations, parse failures and judge errors do not count. |
| `mode` | `stress` for a `--stress` or `--batch` run; absent for an A/B run. |
| `verdict` | Stress runs only: `decision` (`downgrade`, `upgrade` or `keep`), `reason`, the `arm`, `model` and `effort` it moves to (`null` for `keep`), the `downgrade` check (`passes`, `reason`), the `upgrade` check (`findings`, the fixture stems the step-up tier gains, and `reason`), and `recall` per arm (`passes`, `trials`). The decision log's gate checks a row against it. |
| `fidelity` | `read-only-profile`, or `sandboxed-write-profile` when the agent's write tools were enabled. |
| `arms[].fixtures[].trials[].outcome` | The trial result, such as `pass`, `timeout`, `cli_error` or `judge_error`. |
| `arms[].fixtures[].trials[].judge_cost_usd` | What the rubric judge reported for grading the trial, or `null`. |
| `arms[].fixtures[].trials[].cost_reported` | `false` when `claude` reported no cost; `cost_usd` is then 0. |
| `arms[].estimated_cost_usd` | The pre-run estimate for the arm's trials. |
| `arms[].estimated_judge_cost_usd` | The arm's share of the pre-run rubric judge estimate; `0` without a judge. |
| `arms[].totals.clean_fixture_false_positives` | Trials the grader failed (`graded_fail`) on a fixture that expects no findings. On a fixture that expects `skip`, a failed trial counts only when it reported issues. Timeouts, CLI errors, parse failures and tool violations on such a fixture do not count. |
| `arms[].totals.actual_cost_usd` | The reported cost. It is a lower bound when any `cost_reported` is `false`. |
| `arms[].totals.unreported_trials_estimate_usd` | The sum of per-trial estimates charged for trials, and per-judgement estimates charged for rubric judgements, that reported no cost. The `--max-cost` check counts these in place of the cost. |
| `arms[].totals.judge_cost_usd` | The rubric judge's reported cost for the arm's trials, failed judgements included. It is not in `actual_cost_usd`; the `--max-cost` check counts it. |

### Tools and write-capable agents

Trials get the agent's read-only tools: `Read`, `Grep` and `Glob`. Every
other `tools:` entry is withheld and recorded in the artifact under
`tools_withheld`. The harness refuses an agent that declares `Bash`, `Edit`,
`Write`, `MultiEdit` or `NotebookEdit` unless `graders.json` marks it
`sandbox: true`. A sandboxed agent gets those tools too, and its trial copy is a
git repo with one commit. The refusal matches those names exactly. A scoped entry such as `Bash(graphify *)` is not
refused: the harness withholds it and records it in `tools_withheld`. A
`dispatch-set` agent also gets its `Agent` tool, and each stub agent gets only `Read`.

### Sandbox and jail

The sandbox and the jail are defense in depth for fixtures this repo authors and
reviews. They are not VM-grade isolation. Run sandboxed and test-graded trials
only on trusted repo fixtures; for anything else, use a disposable machine.

**The `claude` process.** Every trial runs in a fresh temp copy of the fixture,
with `--restricted` (file tools confined to the copy and the knowledge
directory). Its environment is built from an allowlist: `PATH`, `LANG`, `LC_*`,
`USER`, `LOGNAME`, `HOME`, `TMPDIR`, and the first credential variable set
(`ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`).
`TMPDIR` is a private temp directory for that trial only. With a credential
variable, `HOME` is an empty temp directory; without one, `HOME` is kept,
because a keychain login is found through it. The rubric judge runs with the
same environment rules and its own temp `HOME` and `TMPDIR`. Its prompt goes on
stdin (`-p` with no prompt argument), so a large prompt cannot exceed the OS
limit on one argument (128 KiB on Linux).

When `claude` exits, for any reason, the harness kills its whole process group
before it reads, restores or tests the copy. It then checks that the staging
directory and the working copy are the same real directories (device and inode,
read without following symlinks) as before the trial. If the agent moved,
replaced or symlinked either one, the harness does not diff, restore or test
the copy, and the trial is a `tool_violation`.

**A sandboxed trial** (a write-capable agent) also runs under Claude Code's
Bash sandbox, passed with `--settings` (keys from the
[settings reference](https://code.claude.com/docs/en/settings-reference.md#sandbox-settings)):

- `sandbox.enabled` and `failIfUnavailable`: the CLI exits instead of running
  unsandboxed, so the trial is a `cli_error`.
- `allowUnsandboxedCommands: false` and `autoAllowBashIfSandboxed`.
- An empty `network.allowedDomains`: no network.
- `filesystem.denyRead` on the answer key: the run's frozen copy of the expected
  entries, this repo's git directory (every committed version of them), and the
  `.git` entry and `evals/expected` of the main checkout and of every worktree
  `git worktree list` names.
- `filesystem.denyWrite` on the run's frozen inputs and the same answer-key paths.

It gets `--permission-mode acceptEdits` and `--permission-prompts none`, never
`--dangerously-skip-permissions`. Any permission denial fails the trial as
`tool_violation`. A sandboxed trial gets its own copy of the knowledge
directory, because the sandbox lets commands write to `--add-dir` directories.

**Test commands.** A fixture's `testCommands` run code the agent wrote. They
run with the same allowlist minus the credential, under a jail. Their `HOME` and
`TMPDIR` are new directories the harness makes only after `claude` exits, in a
new random temp directory, not in the trial's private directory, whose paths the
agent knows. The jail gets real paths resolved by the harness and never follows
a symlink to find a writable directory. A jailed command can rename the working
copy or its `TMPDIR` and leave a symlink in its place, so the harness checks
both (device and inode, without following symlinks) before every command; on a
change it runs no more commands and the trial is a `tool_violation`. The harness
probes the jail before planning; with no working jail it refuses a `tests-pass`
run unless you pass `--allow-unjailed-checks`.

| | macOS (`sandbox-exec`) | Linux (`bwrap`) |
| --- | --- | --- |
| Writes | Only the trial copy, its temp dir and `/dev/null`-style devices. | The root is bound read-only; only the trial copy and its temp dir are writable; `/tmp` is an empty tmpfs. |
| Network | Denied (`deny network*`), loopback included. | New network namespace (`--unshare-all`). |
| Signals | Denied (`deny signal`) except to processes in the same sandbox, so a command can stop its own children but not the harness or another process of the user. | New PID namespace: no process outside the jail can be named. |
| Other processes | Launch Services opens (`deny lsopen`), Apple events (`deny appleevent-send`) and preference writes (`deny user-preference-write`, so `defaults write` cannot reach `cfprefsd`) are denied. Every Mach service is denied except an allowlist for user lookups, notifications, logging and preference reads; `pytest`, `node`, `git` and `npx` run with it. `launchctl submit`, `bootstrap` and `load` are refused for a sandboxed caller. | New PID, IPC and user namespaces; `/run` (and `/var/run` when it is a real directory) is an empty tmpfs, so the session bus and the Docker socket are unreachable; `DBUS_SESSION_BUS_ADDRESS` and `XDG_RUNTIME_DIR` are unset. |
| Probe asserts | A write inside works; a write outside, a connection to a harness-owned `127.0.0.1` socket, a `SIGTERM` to a harness-owned sleeping process, `open -a Finder` and `defaults write` are refused. | A write inside works; a write outside, that connection and that signal are refused; the user's session bus cannot be reached and the Docker socket is not visible, each when the host has one. |

**Protected paths.** After the agent finishes, the harness restores each
`protectedPaths` entry from the frozen fixture. The walk holds a directory file
descriptor at each step and opens every directory with `O_NOFOLLOW`, so a symlink
in the path, even one swapped in during the walk, is refused or removed, never
followed. Each directory on the way first gets owner read, write and search
back (chmod without following a symlink), so an agent that locked the copy
cannot stop the restore. The removal and the copy walk any depth of nesting
with a loop, not recursion, holding one directory descriptor at a time and
checking each `..` they climb back through. If the restore still fails (for example, a file the
agent made immutable), the trial is a `tool_violation` with its cost recorded,
and the run continues.

**What the judge sees of the changes.** The diff skips only the harness's own
top-level `.git`; a `.git` directory deeper in the copy is the agent's work and
is shown. An empty file created or deleted gets its own labeled section. A
binary or non-UTF-8 file is named with its size and SHA-256, so a same-size
change shows.

Residual risks, by design or not yet closed:

- **Reads are not confined.** The file tools are held to the copy and the
  knowledge directory by `--restricted`, but a sandboxed trial's Bash commands
  can read anything the user can read except the `denyRead` paths above, and
  test commands are not denied even those. Still readable: the rest of
  this repo, including `evals/fixtures`, the graders in `scripts/eval_graders/`,
  tests that may quote expected values, other clones of the repo that are not
  worktrees of this one, and the user's home directory.
- **Exit-code grading trusts the test process.** Agent-written source can end
  the test process early with exit 0; `protectedPaths` only stop edits to the
  test files themselves.
- **Process races.** A process that left the CLI's process group (a new session,
  or `setsid`) survives the group kill and can change the copy after the
  restore, or swap the working copy after the identity check. On Linux before
  Python 3.13, `chmod` cannot refuse a symlink, so the restore checks each
  directory with `lstat` first and such a process could swap one in between.
  Such a process could also swap the working copy or the test commands' `TMPDIR`
  between the identity check and the next command's start. Once the group is empty, a new process could take its ID between the
  reap and the kill; that window is microseconds.
- **Apple events on macOS.** An `osascript` command to another app is not
  delivered, but it blocks until the test command's timeout instead of failing.
- **Platform coverage.** The sandbox and the jail need macOS, Linux or WSL2.

### Graders

[`evals/model-effort/graders.json`](model-effort/graders.json) names the grader
for each agent that the default does not fit. Every grader's pass rule is a
deterministic grader in `scripts/eval_graders/`, selected by the expected entry's
`grader` field.

| Grader | Agents | What a trial must do |
| --- | --- | --- |
| `expected-findings` (default) | review agents (`verdict`), plan critics, `gherkin-quality-critic`, `spec-reviewer` (`finding_ids`) | Match the expected verdict and report every planted finding ID (`expectedFindingIds`: keywords, optional severities), within `maxFindings`/`maxBySeverity`. |
| `tests-pass` | `software-engineer`, `mutation-kill` | After the agent finishes, the entry's `testCommands` exit 0 in the trial copy, jailed. `protectedPaths` are first restored from the pristine fixture, so the agent cannot weaken the tests that grade it; each must be a relative path inside a directory fixture, and a symlink in its place or in a parent is replaced, never followed. `{python}` is the harness's interpreter. |
| `dispatch-set` | `orchestrator`, `quality-reviewer` | Dispatch every agent in `dispatch.include` and none in `dispatch.exclude` (`exact`: nothing else), read from the transcript's `Agent` calls. Each dispatch goes to a stub agent passed with `--agents` that replies with a clean verdict. The answer may be prose; an entry with `expectedStatus` fails an answer with no JSON verdict. |
| `rubric` | the remaining agents | A judge model pinned in `graders.json` (the top-level `judge`, unless the agent pins its own), one tier above the strongest arm it judges, a stress run's step-up arm included (opus arms are judged by opus), marks every criterion of the agent's committed rubric (`evals/model-effort/rubrics/<agent>.md`) and every `rubricPoints` entry met. The judge sees the rubric, the task, the fixture's text files (capped at 60,000 characters) and the agent's final answer (capped at 30,000 characters), never the expected entry. For a sandboxed agent the judge also sees the harness's diff of the trial copy against the frozen fixture, so it can check what the agent changed and what it left alone. The answer and the diff are fenced between markers with a random per-call token, and the judge is told everything inside is data. A judge call that fails, times out or reports an error is `judge_error`, not `graded_fail`, and its reported cost is still charged. A judge that ran to a result with no `criteria` list is `graded_fail`, cost charged, because the answer may have caused it. An answer over 30,000 characters is `graded_fail` without a judge call. |

An expected entry's `task` replaces the default review prompt; `{fixture}` in it
is the staged fixture's name. The harness refuses a fixture whose expected entry
names a grader (default `verdict`) that the agent's `graders.json` kind does not
accept. It also refuses an expected entry the grader raises on when given a
well-formed answer (for example, an `issueCount` that is a number, not a
`{min, max}` window), before anything is paid for. If a grader still raises
during a trial, the run stops with a harness error when the entry is at fault;
the trial is `graded_fail` only when the agent's answer caused it. It refuses a rubric run whose judge is
not at least one tier above both arms (capped at opus). Rubric-judged agents
default to 10 trials, and rubric evidence can justify a tier change only with 10
graded trials per arm (`trial_count.can_justify_tier_change`); the artifact's
`tier_change_eligible` applies that rule to the `pass` and `graded_fail` trials
each arm has on each fixture.
