---
name: agent-eval
description: >-
  Run eval fixtures against review agents and grade results. Use this after
  adding or modifying a review agent, to validate detection accuracy, or
  when the user says "run the evals", "test the agents", "check for
  regressions", or "how accurate is the agent".
argument-hint: "[--agent <name>] [--skill <name>] [--fixture <name>] [--trials <n>] [--in-session] [--verbose]"
user-invocable: true
allowed-tools: >-
  Read, Grep, Glob,
  Bash(readlink *, ls *, date *, mkdir *, command -v claude, claude -p *),
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
- `--verbose`: Show full agent output for each fixture
- No arguments: run all agents against all applicable fixtures

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

First resolve the dispatch mode (see *Dispatch mode* above):

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
     `claude -p "/test-design-advisor <fixture-path>" --output-format json`.
   - **`--in-session`:** invoke the skill in this session.
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
  --append metrics/eval-variance.jsonl -o memory/eval-variance.json
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
