---
name: human-oversight-protocol
description: Approval gates, intervention commands, and transparency requirements. Use to classify any agent action as autonomous/notify/approve, respond to override/pause/stop commands, or structure a plan review before the implementation phase begins.
role: orchestrator
user-invocable: true
---

# Human Oversight Protocol

## Constraints

- Approval gates cannot be skipped; do not proceed past a gate without explicit human sign-off.
- Ethical concerns are never auto-resolved; always escalate.
- Intervention commands (`override`, `pause`, `stop`) take immediate effect with no debate.
- Overrides accumulate; 3+ overrides on the same topic must trigger a config amend.

## Plan Review as Primary Quality Gate

The implementation plan is the primary review artifact, not the code. Traditional line-by-line code review is replaced by plan review for AI-generated work — 200 lines of plan is far more reviewable than 2,000 lines of generated code, and if the plan is correct and tests pass, the code is trustworthy.

### Plan review checklist

1. Does the research accurately describe how the system works? (File paths, data flows, dependencies)
2. Does the plan address the right problem?
3. Are the specified changes complete — no missing files or edge cases?
4. Is the test strategy sufficient to verify correctness?
5. Are there architectural concerns the plan missed?

### When to still review code

- Security-sensitive paths (authentication, authorization, crypto)
- Performance-critical paths
- When tests are insufficient to verify correctness
- When the plan was ambiguous about implementation details

## Approval Gates

### Gate classification

Every agent action falls into one of three categories:

| Category | Description | Human involvement |
|---|---|---|
| **Autonomous** | Routine work within agent's defined scope | None — deliver output directly |
| **Notify** | Significant but within scope; human should be aware | Deliver output + flag what was decided and why |
| **Approve** | Outside routine scope or high-impact; human must sign off | Present proposal, wait for explicit approval |

### Standard approval gates

These actions always require human approval:

| Action | Rationale |
|---|---|
| Research findings (Phase 1 → 2) | Misunderstanding cascades into bad plans and bad code |
| Implementation plan (Phase 2 → 3) | Plan correctness determines code correctness |
| Production deployment | Irreversible, affects users |
| Architecture change | High-impact, hard to reverse |
| Database schema migration | Data integrity risk |
| Security-sensitive code | Vulnerability risk |
| Scope change | May affect timeline/budget |
| New external dependency | Supply chain risk |
| Delete files or data | Potentially irreversible |
| Team structure change | Affects all agents |

### Agent-specific gates

Each agent defines additional gates in its `## Behavioral Guidelines > Decision Making` section. The Orchestrator consolidates these when coordinating multi-agent tasks.

## Intervention Mechanisms

### 1. Feedback (real-time correction)

```
amend: [modify existing behavior]
learn: [teach something new]
remember: [persist a preference]
forget: [remove a preference]
```

- Does NOT stop the current task
- Agent incorporates the feedback and continues
- Full procedure: [Feedback & Learning](../feedback-learning/SKILL.md)

### 2. Override (decision reversal)

```
override: [what was decided] → [what should be done instead]
```

- Stops the current approach; agent adopts the human's decision without debate
- Logged as override in the audit trail
- 3+ overrides on the same topic should trigger a config amend

### 3. Pause (temporary halt)

```
pause
```

- Agent stops and presents current state
- Human reviews and either resumes or redirects
- No output is discarded

### 4. Stop (emergency halt)

```
stop
```

- All agents halt immediately
- Current output preserved but not delivered
- Orchestrator presents a summary of what was in progress
- Human decides: resume, redirect, or abandon

## Transparency Requirements

### Decision logging

| Log entry | Where | When |
|---|---|---|
| Agent selected for task | Task metrics entry | At task start |
| Routing rationale | Orchestrator metrics entry | At task start |
| Approval gate triggered | Task metrics entry | When gate fires |
| Human approval/rejection | Config changelog | When human responds |
| Override applied | Config changelog | When override issued |

### Decision visibility (Notify level)

```
Decision: [what was decided]
Rationale: [why]
Alternatives considered: [what else was evaluated]
```

### Audit trail

All oversight events logged to `metrics/config-changelog.jsonl` with:
- `type`: `approval` | `override` | `pause` | `stop`
- `trigger`: `user`
- `description`: what happened and why

## Output

Gate classification (autonomous / notify / approve) with rationale, or escalation summary with severity and recommended action. One decision per output; no restating of protocol rules.

## Escalation Paths

```
Agent → Orchestrator → Human
```

1. Agent identifies the issue and flags it to the Orchestrator.
2. Orchestrator classifies severity:
   - **Low**: route to another agent with appropriate expertise
   - **Medium**: present options to human with recommendation
   - **High**: present to human with full context, no recommendation (avoid anchoring)
3. Human decides.
4. Decision logged and fed back to the requesting agent.
