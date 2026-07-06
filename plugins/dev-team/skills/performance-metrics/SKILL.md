---
name: performance-metrics
description: Log task completion data to metrics/. Use at the end of every task to record tokens, cost, agents used, rework cycles, and hallucination events. Also use for periodic reporting to identify efficiency and quality trends.
role: worker
user-invocable: true
---

# Performance Metrics

## Overview

Schema and procedures for capturing performance data in `metrics/`. Metrics enable evidence-based evaluation of agent effectiveness, cost efficiency, and quality outcomes.

## Constraints

- Never log credentials, API keys, or PII in metric entries
- Log entries are append-only; do not modify or delete existing JSONL records
- Log at task completion, not mid-task; mid-task state belongs in `memory/` progress files
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

Metrics are stored in `metrics/` as JSONL files (one JSON object per line).

### File Naming

```
metrics/{date}-task-log.jsonl
```

Example: `metrics/2026-02-20-task-log.jsonl`

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

### Review Value Entry (#348)

`/build` appends one entry per **inline review checkpoint** to
`metrics/review-value.jsonl` so the pipeline's review overhead becomes
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
  "agents_run": ["spec-compliance-review", "security-review"],
  "issues_found": 1,
  "issues_fixed": 1,
  "fix_iterations": 1,
  "outcome": "fixed"
}
```

| Field | Type | Description |
| --- | --- | --- |
| `checkpoint` | string | `step` (per-step `complex` review) or `slice` (batched slice-boundary review) |
| `step` | string | `N.M` for a per-step checkpoint; `all` for a batched slice checkpoint |
| `agents_run` | string[] | Review agents and static-analysis lane tools run at this checkpoint |
| `issues_found` | number | Actionable issues the checkpoint surfaced (semantic review + static lanes) |
| `issues_fixed` | number | Of those, how many were auto-fixed |
| `fix_iterations` | number | Review-fix and static self-heal fix-loop iterations consumed |
| `outcome` | string | `no-op` (passed clean), `fixed` (found + fixed), `escalated` (a fix loop didn't converge — including a static lane capping out) |

**Privacy:** counts and outcomes only — never prompt text, code, or file content,
consistent with the cost meter's privacy boundary. Disable with
`DEV_TEAM_REVIEW_VALUE=off`. Report it with `/cost-report` (its "review value"
section).

### Verify Log Entry (#727)

`/build` appends one entry per **slice with a runtime surface** to
`metrics/verify-log.jsonl` (sub-step 4.9) — evidence that `/verify` actually
exercised the change end-to-end before the slice was marked done, or was
explicitly skipped because the diff had no runtime surface to drive. This is
the sensor that closes the gap the #727 investigation found: a "done" feature
that fails the first time it's really run means `/verify` was either skipped
or never mandated in the first place.

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
| `branch` | string | Current branch name — `scripts/progress_guardian.py --pre-pr` matches on this |
| `files` | string[] | The slice's changed runtime files that `/verify` was scoped to |
| `outcome` | string | `ran` (`/verify` executed and passed), `skipped` (no runtime surface — see `reason`), or `failed-then-fixed` (`/verify` failed at least once before the fix landed) |
| `reason` | string \| null | Required when `outcome` is `skipped` (e.g. `"tests-only"`, `"docs-only"`); `null` otherwise |

**Not disableable.** Unlike Review Value logging (`DEV_TEAM_REVIEW_VALUE=off`),
there is no env var to turn this off — `scripts/progress_guardian.py --pre-pr`
fails closed on a branch with runtime-surface changes and no matching entry,
and that gate is a correctness control, not a metrics-collection nicety.

## When to Log

| Event | Action |
| --- | --- |
| Task completed | Log full task completion entry |
| `/build` inline review checkpoint | Append a Review Value entry to `metrics/review-value.jsonl` (#348) |
| `/build` slice with a runtime surface | Append a Verify Log entry to `metrics/verify-log.jsonl` (#727) |
| Configuration change | Log in `metrics/config-changelog.jsonl` (see Feedback & Learning skill) |
| Hallucination detected | Flag in task entry + log separately if correction applied |
| Context summarization triggered | Increment counter in current task entry |

## Output

JSONL log entries written to `metrics/` and/or a summary report of metric trends. Be concise — report anomalies and trend signals; omit entries within normal range.

## Reporting

Periodically review metrics to identify patterns:

1. **Weekly**: Review task completion entries for rework trends and hallucination rate
2. **Monthly**: Aggregate cost metrics and LLM routing distribution
3. **Per-project**: Compare first-pass acceptance rate across task types

Summaries can be written to `metrics/reports/` for historical reference.
