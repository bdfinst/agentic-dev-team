# Code Review Scoring Rubric

The orchestrator reads this file during Step 5 to compute the overall
health score from individual agent results.

## The review-agent panel is the primary quality gate

The review-agent panel is the primary quality gate for structural quality
(Rec 5, `docs/experiments/RECOMMENDATIONS.md`). Coverage, mutation score, and
the informational Farley Score are **saturating metrics**: every workflow
shape drives them to near-identical values, so they cannot rank structural
quality and must never gate or rank workflows. A higher mutation score must
never be treated as evidence that a costlier workflow — or the code it
produced — is better; in the experiment line the losing arms posted the
higher mutation scores. Score health from the agent verdicts below, nothing
else.

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
| Accessibility | a11y-review | Normal scoring |
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
