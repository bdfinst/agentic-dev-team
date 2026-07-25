---
name: agent-eval
description: >-
  Run eval fixtures against review agents and grade results. Use this after
  adding or modifying a review agent, to validate detection accuracy, or
  when the user says "run the evals", "test the agents", "check for
  regressions", or "how accurate is the agent".
argument-hint: "[--agent <name>] [--skill <name>] [--fixture <name>] [--trials <n>] [--in-session] [--integration] [--ablation <agent>] [--no-cache] [--verbose]"
user-invocable: true
allowed-tools: >-
  Read, Grep, Glob,
  Bash(readlink *, ls *, date *, mkdir *, command -v claude, claude -p *,
       python3 scripts/eval_cache.py *, python3 scripts/run_integration_eval.py *,
       python3 scripts/eval_variance.py *, python3 scripts/eval_ablation.py *,
       python3 scripts/citation_lint.py *),
  Skill(review-agent *), Skill(test-design-advisor *)
---

# Agent Eval

Role: orchestrator. This skill dispatches fixtures to agents and
grades results — it does not review code itself.

You have been invoked with the `/agent-eval` skill. Run review agents
against eval fixtures and grade the results.

## Orchestrator constraints

1. **Do not review or design yourself.** Delegate reviews to
   `/review-agent` and advisory analysis to the skill under eval (e.g.
   `test-design-advisor`). Your job is dispatching and grading.
2. **Grade deterministically.** Compare agent JSON output against
   expected JSON using exact criteria (status match, count ranges,
   keyword checks). Do not apply judgment.
3. **Minimize context per agent.** Pass only the fixture file to the
   agent — not the expected results, not other fixtures, not prior
   transcripts.
4. **Track results.** Save transcripts for saturation detection. Do
   not modify fixtures or expected files.
5. **Be concise.** Output the report table and failure details. No
   narration of each fixture run — just the grades.

## Parse Arguments

Arguments: $ARGUMENTS

- `--agent <name>`: Run only the named review agent
  (e.g., `js-fp-review`)
- `--skill <name>`: Run only the named advisory skill
  (e.g., `test-design-advisor`) against its skill fixtures
- `--fixture <name>`: Run only the named fixture
  (e.g., `fp-array-mutations.ts`)
- `--trials <n>`: Run each fixture N times (default: 1). Enables
  pass@k scoring.
- `--in-session`: Dispatch agents in this session instead of a fresh
  subprocess (see *Dispatch mode* below). Faster, but evaluates the
  agent definitions as already loaded — use only for cheap re-grades
  when no agent/skill file has been edited since they were loaded.
- `--integration`: Dispatch the **integration tier** instead of the unit
  tier (see *Confidence pyramid* below). Routes fixtures that declare an
  `integration` block in their expected JSON through
  `scripts/run_integration_eval.py` (orchestrator dispatched against a
  spec in an ephemeral worktree, then the fixture's `testCommands` are
  graded by the `integration` grader). Cannot be combined with `--agent`
  or `--skill` — integration fixtures target the orchestrator, not a
  single reviewer.
- `--ablation <agent>`: Causal drop-candidate evidence (#868). Implies the
  integration tier and runs it **twice** — a baseline arm (full review-agent
  roster) and an ablated arm (roster minus `<agent>`) — K=3 trials per arm,
  then reports the outcome delta (issues caught, `testCommands` results,
  token cost). See *Ablation mode* below for the full procedure. Rejected
  in combination with `--agent`/`--skill` (integration fixtures target the
  orchestrator) and with more than one target agent — v1 supports exactly
  one ablated agent per run: "error: --ablation supports exactly one agent
  per run (v1); combining with --agent/--skill or naming multiple agents
  is not supported."
- `--no-cache`: Bypass the fingerprint replay cache (see *Cache*
  below). Default is cache-on, so a pair whose transitive inputs are
  unchanged replays from `evals/.eval-cache.json` at zero token cost.
  Use `--no-cache` when you suspect cache corruption or want a clean
  cost baseline.
- `--verbose`: Show full agent output for each fixture
- No arguments: run all agents against all applicable fixtures

## Confidence pyramid

`/agent-eval` dispatches at one of three tiers, in increasing confidence and
cost. See [ADR 0007](../../../../docs/adr/0007-eval-confidence-pyramid-tier-vocabulary.md)
for the full vocabulary; this skill is responsible for selecting the tier and
routing to the right runner.

- **Unit** (default) — one reviewer or one advisory skill against one fixture,
  graded by the `verdict` or `skill_gate` grader. Cheap, deterministic, used
  for every reviewer change. This is what runs when neither `--integration`
  nor any tier-specific flag is set.
- **Integration** (`--integration`) — the orchestrator builds against a
  golden-repo spec in an ephemeral worktree; the fixture's `testCommands` must
  all exit 0 (graded by the `integration` grader). Validates that a plan
  produces code that compiles and passes tests, not just that a reviewer
  flagged the right thing. Opt-in, costs orchestrator + builder tokens.
- **Acceptance** — production-style runs over real PRs / merged code,
  scheduled outside this skill (the live regression gate in CI).
  `/agent-eval` does not dispatch acceptance directly; mention it for
  context only.

When the operator does not specify a tier, run **unit** and report in the
final table how many fixtures would have routed to integration (the count of
expected JSON files whose `integration` block is non-empty). That nudge keeps
integration coverage visible without forcing every run to pay for it.

## Ablation mode (`--ablation <agent>`, #868)

Gives `/harness-audit` **causal** drop-candidate evidence instead of the
correlational usage data it derives from `.claude/metrics/review-value.jsonl` alone:
does removing this agent from the roster actually change integration-tier
pipeline outcomes?

**OPT-IN / LABEL-GATED — same policy as the integration tier (#134).** Before
doing anything else, confirm the opt-in gate is present (a `run-integration`
/ live-eval label on the invoking issue or PR, or the operator explicitly
confirming a live, cost-incurring run in this session). If the gate is
absent:

```text
refused: --ablation requires the label-gated live-eval opt-in (#134) — the
same policy that gates the integration tier. Add the `run-integration` label
or have the operator explicitly confirm a live run, then retry. Nothing was
dispatched; nothing was written to .claude/metrics/.
```

Stop there — dispatch nothing, write nothing to `.claude/metrics/`.

**Argument validation.** Reject before any dispatch if `--ablation` is
combined with `--agent`/`--skill`, or if more than one agent is named (v1 is
single-agent only — see *Parse Arguments* above for the exact error text).

**Fixtures.** Default to every expected JSON with a non-empty `integration`
block (narrow with `--fixture <name>`).

**Cost estimate + explicit confirmation — before any dispatch.** Two arms
(baseline, ablated) × K=3 trials each × the number of selected fixtures is
6× the integration tier's normal per-fixture cost. Print an estimate before
dispatching the first trial of either arm:

```text
Ablation cost estimate: <agent> × <N> fixture(s) × 2 arms × 3 trials = <6·N>
integration dispatch(es). Prior integration runs on this fixture set
averaged ~<tokens> tokens/dispatch (or: "no prior run recorded — using the
integration tier's stated per-dispatch heuristic"), so expect roughly
<estimate> tokens total. Proceed? [y/N]
```

Declining aborts immediately — zero tokens spent, nothing written.

**Dispatch — cache bypassed.** Both arms must be live to be comparable, so
skip the fingerprint-replay cache pre-flight entirely for ablation arms (same
stance as the plain integration tier). For each selected fixture, run 3
trials of each arm, writing each trial's actuals to its own file under a
per-arm trials directory:

```bash
# baseline arm (full roster) — repeat 3x into baseline-trials/trial-<n>.json
python3 scripts/run_integration_eval.py --fixtures-dir evals/fixtures \
  --expected-dir evals/expected --only <fixture> --model <model> \
  --out baseline-trials/trial-1.json
# ...trial-2.json, trial-3.json

# ablated arm (roster minus <agent>) — repeat 3x into ablated-trials/
python3 scripts/run_integration_eval.py --fixtures-dir evals/fixtures \
  --expected-dir evals/expected --only <fixture> --model <model> \
  --ablate-agent <agent> --out ablated-trials/trial-1.json
# ...trial-2.json, trial-3.json
```

`--ablate-agent <agent>` scopes `DEV_TEAM_ABLATE_AGENT=<agent>` to that one
subprocess's environment — no file mutation, no cleanup risk; the roster
reverts the instant the subprocess exits. Never edit an agent/skill file to
achieve the exclusion.

**Delta computation and persistence.** Hand both trial directories to
`scripts/eval_ablation.py --mode agent` — the deterministic, model-free half
that grades each arm (pass@k over the 3 trials, per the same machinery
`eval_variance.py` uses for `--trials`) and computes the delta:

```bash
python3 scripts/eval_ablation.py --mode agent \
  --expected-dir evals/expected \
  --baseline-trials-dir baseline-trials --ablated-trials-dir ablated-trials \
  --ablated-agent <agent> --model <model> \
  --append metrics/eval-ablation.jsonl
```

This appends one `schema: "eval-ablation/v1"` JSONL record (`recorded_at`,
`ablated_agent`, `fixtures`, `model`, `baseline`/`ablated`/`delta` — each
covering `issues_caught`, `test_commands`(_passed for delta), `tokens` — and
`verdict`). **A failing baseline arm blocks any drop/retain claim**: the
script itself forces `verdict: "baseline failed — inconclusive"` when the
baseline didn't pass every trial — report that plainly, do not paraphrase it
into a drop/retain recommendation.

**Console report.** Show a small table: baseline vs ablated vs delta for the
three dimensions, the verdict, and the path (`metrics/eval-ablation.jsonl` —
deliberately not relocated under `.claude/`) the record was appended to.

## Cache (fingerprint replay)

`scripts/eval_cache.py` SHAs each `fixture::target` over the target's
definition + the **transitive closure** of files it reaches (knowledge/,
skills/) + the fixture + expected JSON + grader version. An unchanged SHA
with a stored PASS replays at zero token cost; any changed input busts the
cache.

Default behaviour (cache-on):

1. Before dispatch, run `python3 scripts/eval_cache.py --plan
   --replay-out replay.json` over the resolved fixture/target pair list.
   This produces the **hit/miss** split.
2. Dispatch ONLY the misses through Step 3.
3. After grading, run `python3 scripts/eval_cache.py --store --actuals
   actuals.json` to memoize the new passes.
4. Report `cache: <hits>/<total> replayed at $0` in the summary.

`--no-cache` skips steps 1-3 and dispatches everything. Use it only when you
suspect the cache is wrong; the cache busts automatically on any input
change, so there is normally no operator decision to make.

## Cites: enforcement (drift prevention for the evals themselves)

This skill grades reviewers; if a reviewer carries thresholds with no
`Cites:` declaration, `/agent-eval` is grading drift it cannot detect. Before
dispatching a `--agent <name>` run:

1. Probe `python3 scripts/citation_lint.py --plugin-root plugins/dev-team
   plugins/dev-team/agents/<name>.md`.
2. If it emits an `advisory — states N normative token(s) ... declares no
   Cites:` warning, surface that **once** above the run report:

   ```text
   ⚠ agent <name> states N numeric threshold(s) on RFC-2119 lines but has no
     Cites: declaration. Eval results will not catch drift in those
     thresholds. Add a Cites: list naming the canonical sources.
   ```

3. Continue with dispatch — the warning is advisory, never blocking (matches
   the Phase-1 lint contract).

This makes the eval skill itself a regression guard against threshold drift,
not just a grader for it.

## Dispatch mode

The agent and skill definitions under eval are **plain files on disk**. An
eval is only honest if it grades what is *currently on disk*, not a copy that
was loaded into this session before you started editing.

- **Default — fresh subprocess (disk is authoritative).** Each fixture/agent
  pair is dispatched via a fresh `claude -p` subprocess (Step 3). The
  subprocess loads the agent/skill definitions from disk on every run, so a
  definition you edited a moment ago is reflected immediately. This is the
  correct mode after any edit and the default for that reason.
- **`--in-session` — fast path (no fresh load).** Dispatches via the
  in-session `/review-agent` and skill invocations. This reuses whatever was
  already loaded, so it is cheaper and quicker, but it can evaluate a **stale**
  definition if the file changed mid-session. Use it only for repeated grading
  when you have not touched the agent/skill/knowledge files.

**No silent fallback.** Default mode requires the `claude` CLI on `PATH`. If
`command -v claude` finds nothing, **stop with a clear error** — do not quietly
run in-session, because that would grade a stale definition without the user
knowing:

```text
error: /agent-eval default (fresh-subprocess) mode needs the `claude` CLI on
PATH, which was not found. Install it, or re-run with --in-session to dispatch
in this session (warning: --in-session can grade a stale, already-loaded
definition if you have edited agent/skill files this session).
```

## Steps

### 1. Resolve eval corpus

Verify `.claude/evals/fixtures/` exists. If not, error:
"Cannot find eval fixtures. Expected at `.claude/evals/fixtures/`."

### 2. Load fixtures and expected results

Read all files from `.claude/evals/fixtures/` and corresponding JSON from
`.claude/evals/expected/`.

For each fixture:

- Match the fixture stem (filename without extension) to its
  expected JSON
- For directory fixtures (cs-*), the directory name is the stem
- Parse `applicableAgents` (review-agent fixtures) and/or
  `applicableSkills` (advisory-skill fixtures, e.g. the `tlg-*`
  test-layer-gates corpus) to know what to dispatch. A fixture is an
  **agent fixture**, a **skill fixture**, or both, depending on which
  keys its expected JSON declares.

If `--agent` is specified, filter to fixtures where that agent is in
`applicableAgents`.
If `--skill` is specified, filter to fixtures where that skill is in
`applicableSkills`.
If `--fixture` is specified, filter to that fixture only.

### 3. Run agents against fixtures

If `--ablation <agent>` is set, skip the rest of this section and follow
*Ablation mode* above in full (opt-in gate check, argument validation, cost
estimate + confirmation, two-arm × 3-trial dispatch, delta computation and
persistence, console report). Do not fall through to plain `--integration`
handling below.

If `--integration` is set, skip the rest of this section and dispatch
through `python3 scripts/run_integration_eval.py` for every fixture whose
expected JSON declares an `integration` block. The runner builds the
ephemeral worktree from the fixture's `goldenRepo` tarball, dispatches the
orchestrator against the spec, runs the `testCommands`, records exit codes,
and tears the worktree down unconditionally. Pass the actuals it writes
directly to Step 4 — the `integration` grader will pick them up from the
expected JSON's `integration` block. Skip the cache pre-flight in this
branch for now (cache wiring for the integration tier is tracked separately
to keep the rollout small).

For unit-tier runs, first resolve the dispatch mode (see *Dispatch mode*
above) and consult the cache (see *Cache* above):

- **Default (fresh subprocess).** Run `command -v claude`. If it is missing,
  STOP with the error in *Dispatch mode* — do not fall back to in-session.
  Otherwise dispatch each pair through a fresh subprocess so the definition is
  re-read from disk every run.
- **`--in-session`.** Skip the `claude` check and use the in-session
  invocations described under each pair below.

For each fixture/agent pair (agent fixtures):

1. Dispatch the named review agent against the fixture file/directory:
   - **Default:** a fresh subprocess that reads the agent from disk —
     `claude -p "/review-agent <agent-name> <fixture-path>" --output-format json`
     (add `--model` per the agent's tier when known). Pass **only** the
     fixture path, never the expected JSON.
   - **`--in-session`:** invoke `/review-agent <agent-name>` with the
     fixture file/directory as the target.
2. Parse the agent's JSON output to extract: `status`, `issues[]`,
   `summary`
3. If running multiple trials (`--trials`), repeat and collect all
   results

For each fixture/skill pair (skill fixtures, e.g. `tlg-*`):

1. Dispatch the skill (e.g. `test-design-advisor`) against the fixture file —
   the fixture is a behavior description the advisor designs tests for. Pass
   **only** the fixture file, never the expected JSON.
   - **Default:** a fresh subprocess —
     `claude -p "/test-design --advise --path <fixture-path>" --output-format json`.
     The `test-design-advisor` skill is worker-only; dispatch it through
     `/test-design`, which auto-fires the advisor for a single-file target.
   - **`--in-session`:** invoke the skill in this session via
     `Skill(test-design-advisor, <fixture-path>)`.
2. Capture the advisor's report text — specifically the *Pyramid
   placement* table (the `Gate` column and recommended `Layer`(s)) and
   the surrounding rationale.
3. Repeat per `--trials` as above.

### 4. Grade each result

Compare agent output against expected JSON:

**Status match:**

- Agent status matches `expectedStatus` → PASS
- Agent status is "skip" and fixture is not in
  `applicableAgents` → PASS (correct skip)
- Mismatch → FAIL

**Issue count:**

- `issues.length` within `issueCount.min` to
  `issueCount.max` → PASS
- Outside range → FAIL

**Severity counts:**

- For each severity in expected `severities`, count matching issues
- Count within `min` to `max` → PASS
- Outside range → FAIL

**Keyword checks:**

- For each keyword in `mustMention`: at least one issue message
  contains keyword (case-insensitive) → PASS
- For each keyword in `mustNotMention`: no issue message contains
  keyword → PASS
- Violation → FAIL

**Skill fixtures (gate-firing grade):** for a fixture graded against a
skill, compare the advisor's report (Step 3) to the `skills.<name>`
block:

- **Gate firing** — every gate in `expectedGates` is reflected in the
  report's Gate column / rationale; when `expectedGates` is `[]`, the
  report shows no escalation (Gate cell `—`, no `↑`). Match → PASS.
- **Layer(s)** — every layer in `expectedLayers` appears in the
  *Pyramid placement* recommendation; escalations only raise the layer,
  never lower it. Match → PASS. (`expectedLayers: []` — e.g. the
  ambiguity row — skips this check.)
- **Keyword checks** — `mustMention` / `mustNotMention` are applied to
  the **full advisor report text** (not `issues[]`, which skills don't
  emit), case-insensitive substring, same PASS/FAIL rule as above.

Grade deterministically: the `↑`, `REQUIRED`, `→ cd-test-architecture`,
`approval`/`screenshot`, and `—` sentinels are literal — match them as
written, do not paraphrase.

Each check produces PASS/FAIL. Overall fixture grade: PASS only if
all checks pass.

### 5. Compute pass@k (multi-trial)

If `--trials` > 1:

- pass@1: fraction of fixtures that passed on the first trial
- pass@k: fraction of fixtures that passed on at least one of k
  trials
- Consistency: fraction of fixtures with identical results across
  all trials

**Persist the variance signal (#103).** Write each trial's recorded actuals to a
directory (one JSON per trial — the same `actuals` shape `eval_grade.py` grades),
then aggregate deterministically and append to the trend so stability is tracked
over time, not recomputed and lost:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/../../scripts/eval_variance.py \
  --trials-dir <dir-of-trial-actuals> \
  --append .claude/metrics/eval-variance.jsonl -o .claude/memory/eval-variance.json
```

The report's `quarantine` list names pairs that **flap** (neither always pass nor
always fail). Flaky fixtures should *inform* the #99 CI gate — exclude them from
hard-blocking and report them — rather than cause spurious failures.

### 6. Detect eval saturation

Track the last 3 runs in `.claude/evals/transcripts/`. If the last 3
consecutive runs for an agent produce identical grades, flag as
"saturated" — the expected ranges may need tightening.

### 7. Save transcript

Create `.claude/evals/transcripts/<timestamp>-<agent>.json`:

```json
{
  "timestamp": "2026-03-01T12:00:00Z",
  "agent": "<name>",
  "trials": 1,
  "results": [
    {
      "fixture": "<name>",
      "grade": "pass|fail",
      "checks": {
        "status": "pass|fail",
        "issueCount": "pass|fail",
        "severities": "pass|fail",
        "mustMention": "pass|fail"
      },
      "agentOutput": { "status": "...", "issues": [], "summary": "..." }
    }
  ],
  "summary": {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "passRate": "N%",
    "passAtK": "N%",
    "saturated": ["agent-name"]
  }
}
```

### 8. Generate report

Save to `.claude/evals/reports/<timestamp>-report.md` and display:

```text
# Eval Report — <timestamp>

## Summary
| Metric | Value |
| --- | --- |
| Fixtures | N |
| Passed | N |
| Failed | N |
| Pass rate | N% |
| Pass@k | N% (k=N) |
| Saturated | N agents |

## Results by Agent
| Agent | Fixtures | Passed | Failed | Rate |
| --- | --- | --- | --- | --- |
| js-fp-review | 6 | 5 | 1 | 83% |
| ... | | | | |

## Failures
| Fixture | Agent | Check | Expected | Got |
| --- | --- | --- | --- | --- |
| fp-array-mutations.ts | js-fp-review | issueCount | 4-8 | 2 |
| ... | | | | |

## Saturation Warnings
- js-fp-review: 3 identical runs — consider tightening ranges
```

### 9. Progress tracking

Copy and update this checklist:

```text
- [ ] Eval corpus resolved
- [ ] Fixtures loaded
- [ ] Expected results loaded
- [ ] Agents executed
- [ ] Results graded
- [ ] Transcript saved
- [ ] Report generated
```
