# Plan-review agent rubric

Shared contract for the five adversarial plan-review critics
(`plan-review-acceptance`, `plan-review-design`, `plan-review-parallelization`,
`plan-review-strategic`, `plan-review-ux`), dispatched in parallel before the
human plan-review gate. Each agent cites this file for the "What you
receive" framing and the verdict-aggregation rule below, and keeps its own
domain-specific "What you check", "Severity rules", and full "Output
format" JSON block — the per-agent `issues[]` shape differs too much across
the five (see Output shape below) to collapse into one schema.

## What you receive

- The implementation plan (goal, acceptance criteria, and slices/steps —
  scope varies per agent; see its own "What you check" for what it reads).
- Any spec artifacts (intent, architecture notes, acceptance criteria) if
  they exist.

## Output shape

Four of the five (`plan-review-design`, `plan-review-parallelization`,
`plan-review-strategic`, `plan-review-ux`) share this top-level envelope,
with agent-specific `issues[]` fields (e.g. `files`, `slices`, `category`)
documented in each agent's own "Output format" section:

```json
{
  "reviewer": "<agent name>",
  "verdict": "approve | needs-revision",
  "issues": [
    {
      "description": "<what's wrong>",
      "severity": "blocker | warning"
    }
  ],
  "summary": "<2-3 sentences: overall assessment and top concern>"
}
```

**Documented exception — `plan-review-acceptance`:** it has no top-level
`issues[]` array. It splits findings into four purpose-specific arrays
(`criteria_issues`, `scenario_issues`, `missing_scenarios`, `step_issues`)
instead — see its own "Output format" section, the canonical source for
that shape.

## Verdict rules

- Any `blocker` → `needs-revision`
- 3+ warnings with no blockers → `needs-revision`
- Otherwise → `approve`

**Documented exception — `plan-review-parallelization`:** its threshold is
**2+ warnings** (not 3+), because a same-wave concurrency hazard is riskier
per-occurrence than the other four critics' findings — a wrong wave silently
corrupts work (two agents editing the same file) rather than just producing
a weaker plan.
