---
name: governance-compliance
description: Audit logging, quality gates, and ethics procedures for the agent team. Use for periodic compliance reviews, when logging task completion events, or when an ethical concern arises that requires human escalation.
role: worker
user-invocable: true
---

# Governance & Compliance

## Overview

Requirements and procedures for audit logging, multi-layer quality assurance, and ethical operation of the agent team. Ensures all agent activity is traceable, quality is validated at multiple levels, and ethical principles are maintained.

## Constraints
- The audit changelog is append-only; never modify or delete existing entries
- Never log credentials, API keys, or PII in `metrics/` or `memory/` files
- All agent decisions must be explainable on request — no black-box outputs
- Ethical concerns are never auto-resolved; always escalate to the human

## Audit & Transparency

### What Must Be Logged

| Event | Log Location | Retention |
| --- | --- | --- |
| Task start/completion | `metrics/{date}-task-log.jsonl` | 90 days |
| Configuration change | `metrics/config-changelog.jsonl` | Indefinite |
| Human approval/override | `metrics/config-changelog.jsonl` | Indefinite |
| Hallucination detection | Task log entry (`hallucination_detected` flag) | 90 days |
| Context summarization | `memory/{date}-{task-slug}.md` | 90 days (30 active + 60 archive) |

### Audit Trail Principles
- **Append-only**: Log entries are never modified or deleted
- **Timestamped**: Every entry has an ISO 8601 timestamp
- **Attributed**: Every entry identifies which agent acted and who approved
- **Complete**: No decision-making gap should exist between log entries

### Compliance Queries

To answer "why did the system do X?", trace through:
1. Task log: which agents were involved
2. Config changelog: what configuration was active at the time
3. Memory summaries: what context the agents were working with

## Quality Assurance

### Multi-Layer Validation

Quality is enforced at four progressive layers:

#### Layer 1: Agent Self-Validation
- Every agent applies the [Accuracy Validation](accuracy-validation.md) checklist before delivering output
- Confidence scoring on all major claims
- Tool-based verification for factual claims (file paths, APIs, data)

#### Layer 2: QA Agent Validation
When applicable (code generation, data analysis, architecture changes):
- QA agent reviews output against acceptance criteria
- Automated test generation and execution for code
- Consistency checks against existing codebase

#### Layer 3: Human Spot-Check
- User reviews delivered output
- Feedback captured via accept/reject/amend
- Patterns in rejections feed back through [Feedback & Learning](feedback-learning.md)

#### Layer 4: Post-Hoc Monitoring
- Orchestrator reviews task metrics during learning loop
- Identifies trends: rising rework rate, hallucination frequency, cost outliers
- Triggers configuration amendments when patterns emerge (minimum 3 occurrences)

### Quality Gates

No task output is delivered until it passes applicable quality gates:

| Task Type | Required Gates |
| --- | --- |
| Code implementation | Self-validation + QA review (if available) |
| Architecture design | Self-validation + human approval |
| Documentation | Self-validation + terminology consistency check |
| Bug fix | Self-validation + regression test |
| Data analysis | Self-validation + statistical validation |

## Ethics & Responsibility

### Core Principles

1. **Human accountability**: Humans are ultimately responsible for all outputs. Agents assist and recommend; humans decide and own.
2. **Explainability**: Every agent decision must be explainable. No "black box" outputs. When asked why, the agent must provide rationale.
3. **Bias awareness**: Agents must flag when their output may be influenced by training biases, especially in:
   - Technology recommendations (may favor popular over appropriate)
   - Estimation (may anchor to common patterns)
   - Design decisions (may default to familiar architectures)
4. **Privacy**: Agents must not log, store, or transmit sensitive data (credentials, PII, API keys) in metrics or memory files.
5. **Proportionality**: Agent autonomy should match the risk level of the task. Higher risk = more human oversight.

### Sensitive Data Handling

| Data Type | Rule |
| --- | --- |
| Credentials, API keys | Never log, never store in memory/ or metrics/ |
| PII (names, emails, etc.) | Do not include in metrics entries or summaries |
| Business-sensitive data | Minimize in summaries; use references to source files instead |
| Source code | May be included in summaries when relevant to task continuity |

### When Ethical Concerns Arise

1. Agent identifies the concern and pauses
2. Flags to Orchestrator with: what the concern is, why it matters, what the options are
3. Orchestrator escalates to human (always - ethical concerns are never auto-resolved)
4. Human decides
5. Decision is logged with full rationale

## Output
Compliance checklist results (pass/fail per item) and/or new audit log entries written to `metrics/`. Be concise — report failures and entries written; omit passing items.

## Compliance Checklist

For periodic review (monthly recommended):

- [ ] All tasks in the review period have corresponding log entries
- [ ] No gaps in the config changelog
- [ ] Memory summaries exist for long-running tasks
- [ ] No sensitive data present in metrics/ or memory/ files
- [ ] Hallucination rate is within target (< 5%)
- [ ] Rework rate trend is stable or improving
- [ ] All human overrides have been reviewed for systemic issues
