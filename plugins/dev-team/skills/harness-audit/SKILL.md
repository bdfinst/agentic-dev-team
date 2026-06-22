---
name: harness-audit
description: >-
  Analyze review agent effectiveness, model routing, and orchestration complexity
  against actual usage data. Produces a report of harness components that may be
  candidates for simplification or removal. Use periodically to prevent harness
  staleness as model capabilities improve. Audits the dev-team plugin's OWN
  harness from runtime metrics — not your project repo's readiness (for that,
  use /agent-readiness).
argument-hint: "[--output <path>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash(date *), Write
---

# Harness Audit

Role: orchestrator. This command analyzes harness effectiveness — it does not modify agents or configuration.

You have been invoked with the `/harness-audit` command.

> **Not `/agent-readiness`.** This audits the **dev-team plugin's own harness**
> (review-agent effectiveness, model tiers, orchestration) from accumulated
> runtime metrics in `metrics/`. `/agent-readiness` scores the **subject
> repository's** readiness for AI-assisted development from a static checkout.
> Different subject, different input, different output. The inward-facing
> companion here is `/session-review`, whose `session-digest.jsonl` this command
> consumes (Step 1).

## Orchestrator constraints

1. **Do not modify agents or configuration.** Produce a report only. All remediation requires human action.
2. **Write the report to a file.** Present only the summary table and next-steps in chat — do not repeat the full report.
3. **Be concise.** Use tables and short sentences. No preambles, no filler.

## Parse Arguments

Arguments: $ARGUMENTS

- `--output <path>`: Write report to a specific path. Default: `reports/harness-audit-<date>.md`

## Steps

### 1. Check for metrics data

Read metrics JSONL files from `metrics/`. Two complementary streams exist:

- `metrics/*-task-log.jsonl` — **self-reported** task logs (whatever the model
  chose to record about itself).
- `metrics/session-digest.jsonl` — **ground-truth** real-session digests from
  `/session-review` (#129): token/cost trends, `rework`/`accuracy` counts, and
  `utilization.never_observed_*`. Prefer this where it disagrees with the
  self-reports, and use `never_observed_*` to corroborate stale-component
  flags. Schema + join: see `docs/eval-system.md` → "Session-review trend
  digest".

If no metrics data exists or insufficient data is available (fewer than 10 review runs logged), report:

> "Insufficient metrics data for a meaningful audit. Run the system for a period to accumulate review data, then re-run `/harness-audit`. Minimum: 10 logged review runs."

List what data is missing and exit.

### 2. Analyze review agent effectiveness

For each review agent in the registry (`knowledge/agent-registry.md`):

1. **Finding rate**: How often does this agent produce findings (fail or warn) vs. pass?
2. **Zero-fail agents**: Flag agents that have never returned `fail` across all logged reviews. These are removal candidates — they may not be catching real issues.
3. **False positive rate**: If correction data exists (from `/apply-fixes`), check how often findings were dismissed vs. applied. Agents with >50% dismissed findings have a high false positive rate.
4. **Finding severity distribution**: Is the agent producing mostly minor findings? If >80% of findings are minor severity, consider whether the agent justifies its token cost.

### 3. Analyze model routing

For each agent listed in `knowledge/agent-registry.md` (with model tier from its `model:` frontmatter, resolved via the PreToolUse hook per `agents/orchestrator.md` → Resolution Procedure):

1. **Over-tiered agents**: Agents assigned to opus that consistently produce simple pattern-match findings may work equally well on sonnet or haiku.
2. **Under-tiered agents**: Agents on haiku that frequently miss issues caught by human review may need a higher tier.
3. **Cost distribution**: Which agents consume the most tokens? Are the most expensive agents also the most valuable?

### 4. Analyze orchestration complexity

Review the current pipeline for components that may be unnecessary overhead:

1. **Phase count**: Are all three phases (Research, Plan, Implement) needed for the types of tasks being run? If most tasks are simple, suggest a fast path.
2. **Review checkpoint frequency**: Are inline reviews running on every step? If most steps are trivial, the complexity classification (see `skills/plan/SKILL.md` § Complexity Classification) should be catching this.
3. **Unused skills**: Skills loaded but never applied in logged sessions.

### 5. Produce report

Write the report to the output path using this structure:

```markdown
# Harness Audit Report

**Date**: <date>
**Metrics period**: <earliest to latest logged review>
**Review runs analyzed**: <count>

## Review Agent Effectiveness

### Removal Candidates (zero fail findings)
| Agent | Reviews | Pass rate | Recommendation |
|-------|---------|-----------|----------------|

### High False Positive Rate (>50% dismissed)
| Agent | Findings | Dismissed | Rate | Recommendation |
|-------|----------|-----------|------|----------------|

### Low-Value Agents (>80% minor severity)
| Agent | Findings | Minor % | Recommendation |
|-------|----------|---------|----------------|

## Model Routing Recommendations

| Agent | Current tier | Suggested tier | Rationale |
|-------|-------------|----------------|-----------|

## Orchestration Simplification Opportunities

- <Finding and recommendation>

## Summary

- Agents to consider removing: <count>
- Model tier changes suggested: <count>
- Orchestration simplifications: <count>

## Next Steps

<Actionable recommendations prioritized by impact>
```

### 6. Present results

Display a summary of the report and the file path. Do not repeat the full report in chat — the file is the artifact.

## Error Handling

- Missing metrics files: Report what's missing, suggest how to generate data
- Incomplete agent registry: Flag agents found in metrics but missing from the registry
- No actionable findings: Report that the harness appears well-calibrated — this is a valid outcome
