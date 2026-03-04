---
name: human-oversight-protocol
description: Human approval gates, intervention mechanisms, and transparency requirements for agent oversight
role: orchestrator
user-invocable: true
---

# Human Oversight Protocol

## Overview

Unified protocol for human approval gates, intervention mechanisms, and transparency requirements. Ensures humans maintain oversight of autonomous agent decisions without becoming bottlenecks for routine work.

## Constraints
- Approval gates cannot be skipped; do not proceed past a gate without explicit human sign-off
- Ethical concerns are never auto-resolved; always escalate to the human
- Intervention commands (`override`, `pause`, `stop`) take immediate effect with no debate
- Overrides accumulate; 3+ overrides on the same topic must trigger a config amend

## Philosophy

**Human in the Loop, Not Copilot**: Agents have autonomy to make decisions and act independently within defined boundaries. Humans provide oversight, not step-by-step direction. The system is designed so humans can trust routine output and focus attention on high-impact decisions.

## Plan Review as Primary Quality Gate

In an AI-assisted workflow, the **implementation plan is the primary review artifact**, not the code. Traditional line-by-line code review is replaced by plan review for AI-generated code.

### Why Plan Review Over Code Review
- A bad line of research can produce thousands of bad lines of code
- A bad part of a plan can produce hundreds of bad lines of code
- A bad line of code is just a bad line of code
- 200 lines of implementation plan is far more reviewable than 2,000 lines of generated code
- If the plan is correct and the tests pass, the code is trustworthy
- Human reviewers should read the specs and tests, not every line of code

### Plan Review Checklist
1. Does the research accurately describe how the system works? (File paths, data flows, dependencies)
2. Does the plan address the right problem?
3. Are the specified changes complete — no missing files or edge cases?
4. Is the test strategy sufficient to verify correctness?
5. Are there any architectural concerns the plan missed?

### When to Still Review Code
- Security-sensitive code (authentication, authorization, crypto)
- Performance-critical paths
- When tests are insufficient to verify correctness
- When the plan was ambiguous about implementation details

## Approval Gates

### Gate Classification

Every agent action falls into one of three categories:

| Category | Description | Human Involvement |
| --- | --- | --- |
| **Autonomous** | Routine work within agent's defined scope | None - deliver output directly |
| **Notify** | Significant but within scope; human should be aware | Deliver output + flag what was decided and why |
| **Approve** | Outside routine scope or high-impact; human must sign off | Present proposal, wait for explicit approval |

### Standard Approval Gates

These actions always require human approval regardless of agent:

| Action | Gate | Rationale |
| --- | --- | --- |
| Research findings (Phase 1 → 2 transition) | Approve | Misunderstanding here cascades into bad plans and bad code |
| Implementation plan (Phase 2 → 3 transition) | Approve | Primary quality gate — plan correctness determines code correctness |
| Production deployment | Approve | Irreversible, affects users |
| Architecture change | Approve | High-impact, hard to reverse |
| Database schema migration | Approve | Data integrity risk |
| Security-sensitive code | Approve | Vulnerability risk |
| Scope change | Approve | May affect timeline/budget |
| New external dependency | Approve | Supply chain risk |
| Delete files or data | Approve | Potentially irreversible |
| Team structure change | Approve | Affects all agents |

### Agent-Specific Gates

Each agent defines additional gates in its `## Behavioral Guidelines > Decision Making` section. The Orchestrator consolidates these when coordinating multi-agent tasks.

## Intervention Mechanisms

### 1. Feedback (Real-Time Correction)

Modify agent behavior or output during a task using any feedback keyword:

```
amend: [modify existing behavior]
learn: [teach something new]
remember: [persist a preference]
forget: [remove a preference]
```

- Does NOT stop the current task
- Agent incorporates the feedback and continues
- See [Feedback & Learning](feedback-learning.md) for the full procedure

### 2. Override (Decision Reversal)

Reject an agent's decision and substitute a human decision.

```
override: [what was decided] → [what should be done instead]
```

- Stops the current approach
- Agent adopts the human's decision without debate
- Logged as an override in the audit trail
- Overrides accumulate; 3+ overrides on the same topic should trigger a config amend

### 3. Pause (Temporary Halt)

Halt agent work to allow human review before continuing.

```
pause
```

- Agent stops and presents current state
- Human reviews and either resumes or redirects
- No output is discarded; work continues from the pause point

### 4. Stop (Emergency Halt)

Immediately cease all agent activity.

```
stop
```

- All agents halt immediately
- Current output is preserved but not delivered
- Orchestrator presents a summary of what was in progress
- Human decides how to proceed (resume, redirect, or abandon)

## Transparency Requirements

### Decision Logging

Every non-trivial decision must be traceable:

| What to Log | Where | When |
| --- | --- | --- |
| Agent selected for task | Task metrics entry | At task start |
| Why that agent was selected | Orchestrator's routing rationale | At task start |
| Approval gate triggered | Task metrics entry | When gate fires |
| Human approval/rejection | Config changelog | When human responds |
| Override applied | Config changelog | When override issued |

### Decision Visibility

When an agent makes a decision at the "Notify" level:

1. State the decision clearly
2. State the rationale (why this approach over alternatives)
3. State what was considered and rejected
4. Continue with execution

Format:
```
Decision: [what was decided]
Rationale: [why]
Alternatives considered: [what else was evaluated]
```

### Audit Trail

All oversight events (approvals, overrides, pauses, stops) are logged in `metrics/config-changelog.jsonl` with:
- `type`: `approval`, `override`, `pause`, `stop`
- `trigger`: `user`
- `description`: What happened and why

## Output
Gate classification (autonomous/notify/approve) with rationale, or escalation summary with severity and recommended action. Be concise — one decision per output; no restating of protocol rules.

## Escalation Paths

When an agent encounters something outside its scope:

```
Agent → Orchestrator → Human
```

1. Agent identifies the issue and flags it to the Orchestrator
2. Orchestrator classifies severity:
   - **Low**: Route to another agent with appropriate expertise
   - **Medium**: Present options to human with recommendation
   - **High**: Present to human with full context, no recommendation (avoid anchoring)
3. Human decides
4. Decision is logged and fed back to the requesting agent
