---
name: agent-eval
description: >-
  Run eval fixtures against review agents and grade results. Use this after
  adding or modifying a review agent, to validate detection accuracy, or
  when the user says "run the evals", "test the agents", "check for
  regressions", or "how accurate is the agent".
argument-hint: "[--agent <name>] [--fixture <name>] [--trials <n>] [--verbose]"
user-invocable: true
allowed-tools: >-
  Read, Grep, Glob, Bash(readlink *, ls *, date *, mkdir *),
  Skill(review-agent *)
---

# Agent Eval

Role: orchestrator. This skill dispatches fixtures to agents and
grades results — it does not review code itself.

You have been invoked with the `/agent-eval` skill. Run review agents
against eval fixtures and grade the results.

## Orchestrator constraints

1. **Do not review code yourself.** Delegate all reviews to
   `/review-agent`. Your job is dispatching and grading.
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

- `--agent <name>`: Run only the named agent
  (e.g., `js-fp-review`)
- `--fixture <name>`: Run only the named fixture
  (e.g., `fp-array-mutations.ts`)
- `--trials <n>`: Run each fixture N times (default: 1). Enables
  pass@k scoring.
- `--verbose`: Show full agent output for each fixture
- No arguments: run all agents against all applicable fixtures

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
- Parse `applicableAgents` to know which agents to run

If `--agent` is specified, filter to fixtures where that agent is in
`applicableAgents`.
If `--fixture` is specified, filter to that fixture only.

### 2b. Load pressure scenario fixtures

Check if `.claude/evals/pressure/` exists. If present, load all YAML/JSON fixtures from that directory. Each pressure fixture tests whether a skill prevents a known agent failure mode under adversarial conditions.

**Fixture schema** (all fields required):

```yaml
skill: "test-driven-development"
scenario: "RED-phase rationalization"
adversarial_condition: "Agent receives a complex task and rationalizes skipping RED to save time"
expected_behavior: "TDD skill's Iron Law blocks proceeding without a failing test"
pass_criteria: "Agent writes a failing test before any implementation code"
fail_criteria: "Agent writes implementation code without a preceding failing test"
```

- `skill`: Name of the skill being pressure-tested
- `adversarial_condition`: What the agent is tempted to do (the failure mode trigger)
- `expected_behavior`: What the skill should enforce (the guardrail)
- `pass_criteria` / `fail_criteria`: Binary observable outcome

**Filtering**: If `--agent` is specified, skip pressure fixtures (they test skills, not review agents). If `--fixture` names a pressure fixture, run only that one.

**Malformed fixtures**: If a pressure fixture is missing required fields or fails to parse, report the error — include the filename and which field is missing or malformed — then skip that fixture and continue.

### 3. Run agents against fixtures

For each fixture/agent pair:

1. Invoke `/review-agent <agent-name>` with the fixture
   file/directory as the target
2. Parse the agent's JSON output to extract: `status`, `issues[]`,
   `summary`
3. If running multiple trials (`--trials`), repeat and collect all
   results

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

Each check produces PASS/FAIL. Overall fixture grade: PASS only if
all checks pass.

### 5. Compute pass@k (multi-trial)

If `--trials` > 1:

- pass@1: fraction of fixtures that passed on the first trial
- pass@k: fraction of fixtures that passed on at least one of k
  trials
- Consistency: fraction of fixtures with identical results across
  all trials

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
