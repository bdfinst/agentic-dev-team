---
name: performance-metrics
description: Log task completion data to .claude/metrics/. Use at the end of every task to record tokens, cost, agents used, rework cycles, and hallucination events. Also use for periodic reporting to identify efficiency and quality trends.
role: worker
user-invocable: true
---

# Performance Metrics

## Overview

Schema and procedures for capturing performance data in `.claude/metrics/`. Metrics enable evidence-based evaluation of agent effectiveness, cost efficiency, and quality outcomes.

## Constraints

- Never log credentials, API keys, or PII in metric entries
- Log entries are append-only; do not modify or delete existing JSONL records
- Log at task completion, not mid-task; mid-task state belongs in `.claude/memory/` progress files
- Use the defined JSONL schema; do not invent new top-level fields without updating the reference

## Metric Categories

> **Targets discipline.** Per CLAUDE.md → "Claims discipline", a numeric target
> may only ship if an instrument measures it. The instrumented metrics below cite
> their sensor; the rest read "Aspirational — no sensor yet" until one exists
> (tracked by #102 cost metering and #106 telemetry). Do not reintroduce bare
> numeric targets — `tests/docs/prose_honesty_test.bats` enforces this across all
> shipped prose.

### Efficiency Metrics

| Metric | Description | Target |
| --- | --- | --- |
| Task completion time | Wall-clock time from request to delivery | Track trend, no fixed target |
| Token usage per task | Total input + output tokens consumed | Minimize for comparable quality |
| Agent loading overhead | Tokens spent on agent/skill file reads | Aspirational — no sensor yet |
| Context summarization frequency | How often summarization triggers per task | Aspirational — no sensor yet |

### Quality Metrics

| Metric | Description | Target |
| --- | --- | --- |
| First-pass acceptance rate | Tasks accepted without rework | Aspirational — no sensor yet |
| Rework count | Number of revision cycles per task | Aspirational — no sensor yet |
| Hallucination incidents | Outputs containing fabricated information | Aspirational — no sensor yet |
| Accuracy score | Correctness of structured data extraction | Aspirational — no sensor yet |
| Test coverage | Percentage of code covered by generated tests | Track per project |

### Cost Metrics

| Metric | Description | Target |
| --- | --- | --- |
| Cost per task | Total API cost (input + output tokens at rate) | Track trend |
| LLM routing ratio | Percentage of tasks routed to each LLM | Track distribution |
| Selective loading savings | Tokens saved vs. loading all agents | Aspirational — no sensor yet |

## Log Format

Metrics are stored in `.claude/metrics/` as JSONL files (one JSON object per line).

### File Naming

```
.claude/metrics/{date}-task-log.jsonl
```

Example: `.claude/metrics/2026-02-20-task-log.jsonl`

### Task Completion Entry

Logged at the end of each task:

```json
{
  "timestamp": "2026-02-20T14:30:00Z",
  "task_id": "unique-id",
  "task_type": "implementation",
  "task_description": "Build REST API for user authentication",
  "agents_used": ["software-engineer", "architect"],
  "skills_used": ["hexagonal-architecture"],
  "tokens": {
    "input": 12500,
    "output": 3200,
    "total": 15700
  },
  "cost_usd": 0.043,
  "llm": "opus",
  "handoffs": 0,
  "phases": 2,
  "rework_cycles": 1,
  "accepted": true,
  "hallucination_detected": false,
  "duration_seconds": 180
}
```

### Field Reference

| Field | Type | Description |
| --- | --- | --- |
| `timestamp` | string | ISO 8601 completion time |
| `task_id` | string | Unique identifier for this task |
| `task_type` | string | `implementation`, `design`, `bugfix`, `testing`, `documentation`, `analysis` |
| `task_description` | string | Brief description of the task |
| `agents_used` | string[] | Agent names that were loaded |
| `skills_used` | string[] | Skill names that were loaded |
| `tokens.input` | number | Input tokens from API usage field |
| `tokens.output` | number | Output tokens from API usage field |
| `tokens.total` | number | Sum of input + output |
| `cost_usd` | number | Estimated cost based on token rates |
| `llm` | string | Model ID used |
| `handoffs` | number | Times the handoff skill was triggered (either mode) |
| `phases` | number | Number of loading phases |
| `rework_cycles` | number | Number of revision cycles |
| `accepted` | boolean | Whether the user accepted the output |
| `hallucination_detected` | boolean | Whether a hallucination was flagged |
| `duration_seconds` | number | Wall-clock seconds from start to delivery |

### Cost Metering Entry (#102, #1094)

The `Stop`/`SubagentStop` hook (`hooks/cost_meter.py` →
`hooks/lib/cost_meter.py record`) appends one entry per fire to
`.claude/metrics/cost-metering.jsonl` — the running per-session token/cost summary
parsed from the transcript. Full schema reference:
`knowledge/telemetry-schema.md`.

```json
{
  "timestamp": "2026-07-18T14:30:00Z",
  "transcript": "session.jsonl",
  "total": {"input_tokens": 18000, "output_tokens": 3500, "cost_usd": 0.16, "messages": 12},
  "by_model": {"<model-id>": {"cost_usd": 0.16, "input_tokens": 18000, "output_tokens": 3500}},
  "by_thread": {"main": {"cost_usd": 0.10, "input_tokens": 10000, "output_tokens": 2000},
                "subagent": {"cost_usd": 0.06, "input_tokens": 8000, "output_tokens": 1500}},
  "by_agent_type": {"main": {"cost_usd": 0.10, "input_tokens": 10000, "output_tokens": 2000},
                    "security-review": {"cost_usd": 0.06, "input_tokens": 8000, "output_tokens": 1500}}
}
```

| Field | Type | Description |
| --- | --- | --- |
| `total` | object | Session-cumulative token counts, `cost_usd`, `messages` |
| `by_model` | object | Per-model slim breakdown (`cost_usd`, `input_tokens`, `output_tokens`) |
| `by_thread` | object | `main` vs `subagent`, from the native `isSidechain` flag |
| `by_agent_type` | object | `main` for main-loop turns; sidechain turns keyed by subagent type via the harness-recorded `attributionAgent` field or the Task-dispatch `subagent_type`/`agentId` join; unmappable sidechain spend lands in `unattributed` (#1094) |

**Privacy:** token counts, dollar amounts, model identifiers, and thread/
agent-type identifiers only — never prompt text, code, file paths, or tool
payloads. Attribution reads only fields the Claude Code harness itself writes
to the transcript; the meter never guesses (see #170 for the buckets removed
because the harness records no signal for them). Disable with
`DEV_TEAM_COST_METER=off`. Report it with `/cost-report`.

### Review Value Entry (#348)

`/build` appends one entry per **inline review checkpoint** to
`.claude/metrics/review-value.jsonl` so the pipeline's review overhead becomes
*measurable* — distinguishing a build where review caught and fixed a real defect
from one where every loop passed no-op. This is the sensor that lets the plan/step
tiering (the `/plan` plan-tier and `/build` per-step complexity routing) be
right-sized with evidence rather than guessed.

```json
{
  "timestamp": "2026-06-22T14:30:00Z",
  "plan": "plans/add-auth.md",
  "slice": "2",
  "step": "all",
  "checkpoint": "slice",
  "complexity": "standard",
  "source": "build-checkpoint",
  "agents_run": ["spec-compliance-review", "security-review"],
  "issues_found": 1,
  "severity_breakdown": {"errors": 1, "warnings": 0, "suggestions": 0},
  "issues_fixed": 1,
  "fix_iterations": 1,
  "outcome": "fixed"
}
```

| Field | Type | Description |
| --- | --- | --- |
| `checkpoint` | string | `step` (per-step `complex` review), `slice` (batched slice-boundary review), or `backstop` (the Step-6 backstop pass, #1962) |
| `source` | string | Row provenance — `build-checkpoint` (fix-applying `/build` inline checkpoint, the default when absent), `build-backstop` (fix-applying `/build` Step-6 backstop, #1962), or `code-review` (read-only standalone review). `/harness-audit` Step 4 excludes `code-review` rows from fix-rate drop-candidate logic (#1257); `build-backstop` rows are fix-applying and stay in it, and additionally drive the backstop-redundancy readout that gates `--backstop-review=skip` |
| `outcome` | string | `no-op`, `fixed`, `escalated`, or — backstop rows only — `skipped` when `--backstop-review=skip` suppressed the pass. A `skipped` row records the suppression and is excluded from every rate (#1962) |
| `diff_shape` | string | `test-only` or `mixed`, from `change_shape.py`'s `isTestOnly` (never eyeballed). Splits per-lens outcomes by diff shape so a test-only lens gate can be justified by measurement rather than intuition (#1964) |
| `step` | string | `N.M` for a per-step checkpoint; `all` for a batched slice checkpoint |
| `agents_run` | string[] | Review agents and static-analysis lane tools run at this checkpoint |
| `issues_found` | number | Actionable issues the checkpoint surfaced (semantic review + static lanes) |
| `severity_breakdown` | object | `{errors, warnings, suggestions}` counts (same enum as `/code-review`); the three sum to `issues_found`. Lets `/harness-audit` Step 3 flag low-value (mostly-minor) lenses (#1256) |
| `issues_fixed` | number | Of those, how many were auto-fixed |
| `fix_iterations` | number | Review-fix and static self-heal fix-loop iterations consumed |
| `outcome` | string | `no-op` (passed clean), `fixed` (found + fixed), `escalated` (a fix loop didn't converge — including a static lane capping out) |

**Privacy:** counts and outcomes only — never prompt text, code, or file content,
consistent with the cost meter's privacy boundary. Disable with
`DEV_TEAM_REVIEW_VALUE=off`. Report it with `/cost-report` (its "review value"
section).

### Verify Log Entry (#727)

`/build` appends one entry per **slice with a runtime surface** to
`metrics/verify-log.jsonl` (sub-step 4.9) — evidence that the project's own
test/verification tooling actually exercised the change end-to-end before the
slice was marked done, or was explicitly skipped because the diff had no
runtime surface to drive. This is the sensor that closes the gap the #727
investigation found: a "done" feature that fails the first time it's really
run means runtime verification was either skipped or never mandated in the
first place.

```json
{
  "timestamp": "2026-07-02T14:30:00Z",
  "plan": "plans/add-auth.md",
  "slice": "2",
  "branch": "feat/add-auth",
  "files": ["src/api/auth.py"],
  "outcome": "ran",
  "reason": null
}
```

| Field | Type | Description |
| --- | --- | --- |
| `branch` | string | Current branch name — `${CLAUDE_PLUGIN_ROOT}/scripts/progress_guardian.py --pre-pr` matches on this |
| `files` | string[] | The slice's changed runtime files the verification was scoped to |
| `outcome` | string | `ran` (the verification ran and passed), `skipped` (no runtime surface — see `reason`), or `failed-then-fixed` (the verification failed at least once before the fix landed) |
| `reason` | string \| null | Required when `outcome` is `skipped` (e.g. `"tests-only"`, `"docs-only"`); `null` otherwise |

**Not disableable.** Unlike Review Value logging (`DEV_TEAM_REVIEW_VALUE=off`),
there is no env var to turn this off — `${CLAUDE_PLUGIN_ROOT}/scripts/progress_guardian.py --pre-pr`
fails closed on a branch with runtime-surface changes and no matching entry,
and that gate is a correctness control, not a metrics-collection nicety.

## When to Log

> **Task completion entries are written automatically** by `hooks/task_completion_metrics.py`
> on every `Stop` / `SubagentStop` event — skills no longer need a manual
> "log this on completion" step. To surface task-specific values (task type,
> agents used, hallucination flag, rework count, defect count, or a config
> change), populate `.claude/session-metrics.json` before the session ends; the
> hook reads and clears it. Leave the file absent for a minimal heartbeat entry.

| Event | Action |
| --- | --- |
| Task completed | Logged automatically by `hooks/task_completion_metrics.py` (no manual step needed) |
| `/build` inline review checkpoint | Append a Review Value entry to `.claude/metrics/review-value.jsonl` (#348) |
| `/build` slice with a runtime surface | Append a Verify Log entry to `metrics/verify-log.jsonl` (#727) |
| Configuration change | Add `config_change` to `.claude/session-metrics.json`; hook writes `.claude/metrics/config-changelog.jsonl` |
| Hallucination detected | Set `hallucination_detected: true` in `.claude/session-metrics.json` |
| Context summarization triggered | Increment counter in current task entry |

## Output

JSONL log entries written to `.claude/metrics/` and/or a summary report of metric trends. Be concise — report anomalies and trend signals; omit entries within normal range.

## Reporting

Periodically review metrics to identify patterns:

1. **Weekly**: Review task completion entries for rework trends and hallucination rate
2. **Monthly**: Aggregate cost metrics and LLM routing distribution
3. **Per-project**: Compare first-pass acceptance rate across task types

Summaries can be written to `.dev-team-reports/` for historical reference.
