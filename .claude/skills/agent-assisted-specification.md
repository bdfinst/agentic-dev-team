---
name: agent-assisted-specification
description: Structured workflow for producing specification artifacts before implementation begins
role: worker
user-invocable: true
---

# Agent-Assisted Specification

## Overview

Structured workflow for collaborating with humans to produce four specification artifacts (Intent Description, User-Facing Behavior, Architecture Specification, Acceptance Criteria) before any implementation begins. Ensures clarity, completeness, and consistency for the next single unit of work.

## Constraints
- No code or implementation during the specification phase
- The consistency gate is a hard stop — do not proceed to implementation until it passes
- Each specification covers one vertical slice only; split if scope is too broad
- Max 2 critique-refine iterations per artifact before escalating to the Orchestrator

## Core Concepts

### Specification Artifacts

| Artifact | Purpose | Format |
| --- | --- | --- |
| Intent Description | What the change achieves and why | Plain language, 1-3 paragraphs |
| User-Facing Behavior | Observable behavior from the user's perspective | BDD/Gherkin scenarios |
| Architecture Specification | Where the change fits in the system and what constraints apply | Structured notes: components, interfaces, dependencies, constraints |
| Acceptance Criteria | Non-functional requirements and quality thresholds | Measurable criteria with pass/fail conditions |

### Collaboration Pattern

Every artifact follows the same four-step loop:

1. **Human drafts** — write the first version based on current understanding
2. **Agent critiques** — identify gaps, ambiguities, conflicts, and scope violations
3. **Human decides** — accept, reject, or modify the agent's suggestions
4. **Agent refines** — generate an updated version incorporating human decisions

### Scope Constraint

Each specification covers **one vertical slice** — a single scenario, a single behavior. Scope signals that the change is too broad:

- Specification effort exceeds a short conversation
- More than 3 components are affected
- Multiple independent behaviors are described
- The change cannot be deployed and validated independently

### Critique Categories

| Category | Description |
| --- | --- |
| Gaps | Missing scenarios, unstated assumptions, undefined behavior |
| Ambiguities | Statements that could be interpreted differently by two implementers |
| Conflicts | Contradictions between artifacts or with existing system behavior |
| Scope violations | Change covers more than one vertical slice |

## Patterns

### Artifact Collaboration Loop

| Step | Human Action | Agent Action |
| --- | --- | --- |
| 1. Draft | Write initial artifact | — |
| 2. Critique | — | Identify gaps, ambiguities, conflicts, scope violations |
| 3. Decide | Accept/reject/modify suggestions | — |
| 4. Refine | — | Produce updated artifact incorporating decisions |
| 5. Repeat | Review refined version | If issues remain, return to step 2 (max 2 iterations before escalation) |

### Cross-Artifact Consistency Gate

Before implementation begins, validate all four artifacts as a set:

- [ ] Intent is unambiguous — two developers would interpret it the same way
- [ ] Every behavior in the intent has at least one corresponding BDD scenario
- [ ] Architecture specification constrains implementation to what the intent requires, without over-engineering
- [ ] Same concepts are named consistently across all four artifacts
- [ ] No artifact contradicts another

This gate is a **hard stop**. Do not proceed to implementation until all items pass.

### Scope Split Protocol

When scope-too-large signals fire:

1. Identify the independent behaviors within the oversized change
2. Propose a split into separately deliverable vertical slices
3. Human approves the split before continuing specification on any slice
4. Each slice gets its own full set of four artifacts

## When to Apply

| Scenario | Apply? |
| --- | --- |
| New feature or behavior change | Yes |
| Bug fix with clear reproduction steps | No |
| Refactoring with no behavior change | No |
| Spike or investigation | No |
| Feature modification changing user-facing behavior | Yes |

## When Not to Apply

- Changes with no user-facing behavior impact
- Exploratory work where the goal is learning, not delivery
- Trivial changes where the specification would be larger than the implementation

## Guidelines

1. **No implementation during the specification phase.** Do not generate code, tests, or infrastructure until the consistency gate passes.
2. **Structured critique output.** Agent critiques must be categorized (gap, ambiguity, conflict, scope violation) with specific references to the artifact text.
3. **Preserve human language.** When refining artifacts, keep the human's phrasing where possible. The human owns the specification; the agent improves its precision.
4. **Consistency gate is a hard stop.** No exceptions. Conflicts caught in specification cost minutes; conflicts caught during implementation cost sessions.
5. **Gherkin scenarios are contracts.** BDD scenarios in feature files are the single source of truth for expected behavior. No implementation begins without corresponding scenarios; no scenario exists without a corresponding acceptance test.
6. **Escalate after 2 iterations.** If an artifact does not stabilize after 2 critique-refine cycles, escalate to the Orchestrator for re-scoping or human intervention.
7. **Small batches only.** If the specification cannot fit a single vertical slice, split before continuing.
8. **Document decisions, not just outcomes.** When the human rejects an agent suggestion, briefly note why — this context prevents the same suggestion from recurring.

## Output
Four specification artifacts (Intent Description, User-Facing Behavior in Gherkin, Architecture Specification, Acceptance Criteria) plus a consistency gate pass/fail verdict. Be concise — flag gaps and conflicts; do not narrate the artifact collaboration process.

## Integration

- **Human Oversight Protocol** — the consistency gate is an approval gate; if it fails, the human resolves conflicts before proceeding
- **Accuracy Validation** — agents apply self-validation to their critique output before presenting it
- **Task Review & Correction** — if implementation reveals specification gaps, feed corrections back through the artifact collaboration loop
- **Performance Metrics** — log specification cycle count, consistency gate pass/fail, and scope splits per task
