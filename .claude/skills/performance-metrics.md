---
name: performance-metrics
description: Schema and procedures for capturing performance data and evaluating agent effectiveness
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

### Efficiency Metrics

| Metric | Description | Target |
| --- | --- | --- |
| Task completion time | Wall-clock time from request to delivery | Track trend, no fixed target |
| Token usage per task | Total input + output tokens consumed | Minimize for comparable quality |
| Agent loading overhead | Tokens spent on agent/skill file reads | < 5% of total task tokens |
| Context summarization frequency | How often summarization triggers per task | < 2 per standard task |

### Quality Metrics

| Metric | Description | Target |
| --- | --- | --- |
| First-pass acceptance rate | Tasks accepted without rework | > 80% |
| Rework count | Number of revision cycles per task | < 2 |
| Hallucination incidents | Outputs containing fabricated information | < 5% of tasks |
| Accuracy score | Correctness of structured data extraction | > 95% |
| Test coverage | Percentage of code covered by generated tests | Track per project |

### Cost Metrics

| Metric | Description | Target |
| --- | --- | --- |
| Cost per task | Total API cost (input + output tokens at rate) | Track trend |
| LLM routing ratio | Percentage of tasks routed to each LLM | Track distribution |
| Selective loading savings | Tokens saved vs. loading all agents | > 50% reduction |

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
  "llm": "claude-opus-4-6",
  "context_summarizations": 0,
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
| `context_summarizations` | number | Times summarization was triggered |
| `phases` | number | Number of loading phases |
| `rework_cycles` | number | Number of revision cycles |
| `accepted` | boolean | Whether the user accepted the output |
| `hallucination_detected` | boolean | Whether a hallucination was flagged |
| `duration_seconds` | number | Wall-clock seconds from start to delivery |

## When to Log

| Event | Action |
| --- | --- |
| Task completed | Log full task completion entry |
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
