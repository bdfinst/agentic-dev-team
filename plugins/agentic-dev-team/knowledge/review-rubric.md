# Code Review Scoring Rubric

The orchestrator reads this file during Step 5 to compute the overall
health score from individual agent results.

## Health Score Calculation

Collect the status from each agent: `pass`, `warn`, `fail`, `skip`.

```
🟢 HEALTHY  = 0 fail AND ≤2 warn
🟠 NEEDS ATTENTION = 1-2 fail OR 3+ warn
🔴 CRITICAL = 3+ fail OR any security-review fail
```

Agents that returned `skip` are excluded from scoring.

## Category Weights

Not all agent failures carry equal weight. Security and domain
integrity failures escalate faster than style or naming issues.

| Category | Agents | Escalation |
|----------|--------|------------|
| Security | security-review | Any fail → 🔴 overall |
| Architecture | arch-review, domain-review | 2+ fail → 🔴 overall |
| Correctness | test-review, concurrency-review | Normal scoring |
| Quality | structure-review, complexity-review, js-fp-review, naming-review | Normal scoring |
| Accessibility | a11y-review, svelte-review | Normal scoring |
| Ops | doc-review, claude-setup-review, token-efficiency-review, performance-review | Normal scoring |

## Issue Severity Mapping

Agent issues map to the report as follows:

| Agent severity | Report display | Correction prompt priority |
|----------------|---------------|---------------------------|
| error | 🔴 error | high |
| warning | 🟠 warning | medium |
| suggestion | 💡 suggestion | low |

## Confidence and Actionability

| Confidence | Meaning | Auto-fixable |
|------------|---------|--------------|
| high | Mechanical fix, single correct answer | Yes |
| medium | Direction clear, implementation varies | Yes (with review) |
| none | Requires human judgment | No — report only |
