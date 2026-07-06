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

Read metrics JSONL files from `metrics/`. Full field reference for every
stream below: `${CLAUDE_PLUGIN_ROOT}/knowledge/telemetry-schema.md` — read it
instead of re-deriving a schema from the emitter. Four complementary streams
exist:

- `metrics/*-task-log.jsonl` — **self-reported** task logs (whatever the model
  chose to record about itself).
- `metrics/session-digest.jsonl` — **ground-truth** real-session digests from
  `/session-review` (#129): token/cost trends, `rework`/`accuracy` counts, and
  `utilization.never_observed_*`. Prefer this where it disagrees with the
  self-reports, and use `never_observed_*` to corroborate stale-component
  flags. Schema + join: see `docs/eval-system.md` → "Session-review trend
  digest".
- `metrics/artifact-usage.json` — **per-artifact usage index** written by the
  telemetry hook on each Skill invocation. Use `last_used_at` to identify
  artifacts that have never been observed (absent from the index) or are stale
  (absent or `last_used_at` > 30 days ago). Cross-reference with
  `never_observed_*` in `session-digest.jsonl` for corroboration. See
  `knowledge/artifact-lifecycle.md` for the lifecycle threshold definitions.
- `metrics/boundary-events.jsonl` — **boundary-level (policy-gateway) events**
  (#859): every guard hook's `block`/`warn`/`bypass` decision plus
  `intervention` keywords, each with the emitting `hook` and a `matched_rule`
  rule ID. Where `session-digest.jsonl`'s `rework` counts show outcomes
  without causes, join on `session_id` (when present on both streams) to
  attribute friction to a specific hook/rule instead of reasoning from counts
  alone.

If no metrics data exists or insufficient data is available (fewer than 10 review runs logged), report:

> "Insufficient metrics data for a meaningful audit. Run the system for a period to accumulate review data, then re-run `/harness-audit`. Minimum: 10 logged review runs."

List what data is missing and exit.

### 2. Check for a stale baseline (re-baseline detection, #860)

Report-only — this step never edits `evals/baseline.json` or re-runs evals
itself; it only decides whether the report needs a **Re-baseline Required**
section.

1. Read `evals/baseline.json`. If the file is absent, skip this step
   entirely (nothing to compare).
2. Read its `model` field (written by `scripts/eval_variance.py
   --write-baseline --model <name>`, per the change-contract flow in
   `skills/feedback-learning/SKILL.md`). **Absent field = pre-migration
   baseline — do not prompt.** This is deliberate: a baseline recorded
   before the `model` field existed carries no false signal either way.
3. Read the current session's model from `metrics/session-digest.jsonl`
   (the most recent record's model field) or session metadata.
4. Compare. **On mismatch**, the report (Step 7) gains a **Re-baseline
   Required** section instructing the operator to re-run the eval suite and
   re-write the baseline (`/agent-eval` full suite + `eval_variance.py
   --write-baseline --model <current-model>`) before trusting any pre/post
   comparison elsewhere in this report or in a feedback-learning change
   contract. Flag explicitly that scaffolding kept alive by old-model scores
   (e.g. a removal candidate from Step 3 that "still fails" on the old
   model) may now be re-evaluable and possibly removable.
5. **On match** (or the field absent), no section is added — this is silent
   success, not a finding.

### 3. Analyze review agent effectiveness

For each review agent in the registry (`knowledge/agent-registry.md`):

1. **Finding rate**: How often does this agent produce findings (fail or warn) vs. pass?
2. **Zero-fail agents**: Flag agents that have never returned `fail` across all logged reviews. These are removal candidates — they may not be catching real issues.
3. **False positive rate**: If correction data exists (from `/apply-fixes`), check how often findings were dismissed vs. applied. Agents with >50% dismissed findings have a high false positive rate.
4. **Finding severity distribution**: Is the agent producing mostly minor findings? If >80% of findings are minor severity, consider whether the agent justifies its token cost.

### 4. Analyze review-value fix rates

Read `metrics/review-value.jsonl` (written by `/build` per #348, schema in `performance-metrics`). If the file is absent, note it and continue — this section is skippable.

For each **checkpoint type** (the `checkpoint` field: `step` or `slice`) and each **agent combination** (`agents_run` list, treated as a set-key), compute:

```bash
[ -f metrics/review-value.jsonl ] && jq -s '
  group_by(.checkpoint + "|" + (.agents_run | sort | join(",")))
  | map({
      checkpoint:    .[0].checkpoint,
      agents:        (.[0].agents_run | sort | join(", ")),
      total:         length,
      no_op:         (map(select(.outcome=="no-op"))    | length),
      fixed:         (map(select(.outcome=="fixed"))     | length),
      escalated:     (map(select(.outcome=="escalated")) | length),
      fix_rate:      ((map(select(.outcome=="fixed")) | length) / length * 100 | round),
      issues_found:  (map(.issues_found)  | add // 0),
      issues_fixed:  (map(.issues_fixed)  | add // 0),
      fix_iterations:(map(.fix_iterations)| add // 0)
    })' \
  metrics/review-value.jsonl
```

Flag **drop candidates**: any checkpoint+agents combination with `fix_rate == 0` across **N ≥ 5** logged runs is a drop candidate — it consistently adds overhead without catching defects.

Flag **high-value checkpoints**: `fix_rate ≥ 50%` — these are earning their cost and should be retained.

**Drop-candidate recommendations** (P2-S3):
For each drop candidate emit a recommendation in this form:
> `<checkpoint>/<agents>` fixed 0/<N> runs (fix rate 0%) — candidate to drop. To act: remove this checkpoint type from the relevant `/build` step-complexity tier or exclude these agents from the checkpoint's dispatch list. Do not auto-edit skills; present for human decision.

Do not modify any skill or agent file. The report is the only artifact.

### 5. Analyze model routing

For each agent listed in `knowledge/agent-registry.md` (with model tier from its `model:` frontmatter, resolved via the PreToolUse hook per `agents/orchestrator.md` → Resolution Procedure):

1. **Over-tiered agents**: Agents assigned to opus that consistently produce simple pattern-match findings may work equally well on sonnet or haiku.
2. **Under-tiered agents**: Agents on haiku that frequently miss issues caught by human review may need a higher tier.
3. **Cost distribution**: Which agents consume the most tokens? Are the most expensive agents also the most valuable?

### 6. Analyze orchestration complexity

Review the current pipeline for components that may be unnecessary overhead:

1. **Phase count**: Are all three phases (Research, Plan, Implement) needed for the types of tasks being run? If most tasks are simple, suggest a fast path.
2. **Review checkpoint frequency**: Are inline reviews running on every step? If most steps are trivial, the complexity classification (see `skills/plan/SKILL.md` § Complexity Classification) should be catching this.
3. **Unused skills**: Skills loaded but never applied in logged sessions.

### 7. Produce report

Write the report to the output path using this structure:

```markdown
# Harness Audit Report

**Date**: <date>
**Metrics period**: <earliest to latest logged review>
**Review runs analyzed**: <count>

## Re-baseline Required

> Only present when Step 2 detects a model mismatch between
> `evals/baseline.json`'s `model` field and the current session's model.
> Omit this section entirely on a match or an absent/pre-migration field.

- **Baseline model**: <model recorded in evals/baseline.json>
- **Current session model**: <current model>
- **Action**: Re-run the eval suite and re-write the baseline
  (`/agent-eval` full suite, then `eval_variance.py --write-baseline
  --model <current-model>`) before trusting any pre/post comparison in this
  report or in a feedback-learning change contract.
- **Possibly stale scaffolding**: <any removal candidate below whose
  "zero fail" or "high false positive" verdict was measured on the old
  model — flag for re-evaluation, not automatic removal>

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

## Review-Value Fix Rates (inline checkpoint ROI)

> Source: `metrics/review-value.jsonl`. Absent = no `/build` runs logged yet.

### Per-Checkpoint-Type Fix Rates
| Checkpoint | Agents | Runs | No-op | Fixed | Escalated | Fix rate |
|------------|--------|------|-------|-------|-----------|----------|

### Drop Candidates (fix rate 0%, N ≥ 5 runs)
| Checkpoint | Agents | Runs | Recommendation |
|------------|--------|------|----------------|

> To act on a drop candidate: remove the checkpoint type from the relevant `/build`
> step-complexity tier or exclude the agents from that checkpoint's dispatch list.
> Requires human decision — do not auto-edit skills.

### High-Value Checkpoints (fix rate ≥ 50%)
| Checkpoint | Agents | Runs | Fix rate | Issues fixed |
|------------|--------|------|----------|--------------|

## Model Routing Recommendations

| Agent | Current tier | Suggested tier | Rationale |
|-------|-------------|----------------|-----------|

## Orchestration Simplification Opportunities

- <Finding and recommendation>

## Summary

- Agents to consider removing: <count>
- Model tier changes suggested: <count>
- Orchestration simplifications: <count>
- Review-value drop candidates: <count>
- Review-value high-value checkpoints: <count>
- Re-baseline required: <yes/no>

## Next Steps

<Actionable recommendations prioritized by impact>
```

### 8. Present results

Display a summary of the report and the file path. Do not repeat the full report in chat — the file is the artifact.

## Error Handling

- Missing metrics files: Report what's missing, suggest how to generate data
- Incomplete agent registry: Flag agents found in metrics but missing from the registry
- No actionable findings: Report that the harness appears well-calibrated — this is a valid outcome
