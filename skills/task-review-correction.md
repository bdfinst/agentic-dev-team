---
name: task-review-correction
description: Review completed output, classify defects by severity, and iterate corrections until acceptance criteria are met. Use when output is returned for rework, when peer-reviewing another agent's work, or when self-reviewing before delivery.
role: worker
user-invocable: true
---

# Task Review & Correction

## Overview

Structured workflow for reviewing completed agent output, identifying defects, and iterating corrections until acceptance criteria are met. Fills the gap between pre-delivery validation (Accuracy Validation) and post-hoc learning (Feedback & Learning) by defining a repeatable review-correct-verify loop.

## Constraints
- Max 3 review-correction cycles before escalating to the Orchestrator
- Each cycle must reduce total defect count; flat or increasing defects trigger escalation
- Cascading fixes require verifying related work, not only the isolated change
- Do not use this skill during initial development; use Accuracy Validation instead

## Core Concepts

### Review Types

| Type | Who Reviews | When | Purpose |
| --- | --- | --- | --- |
| Self-review | Delivering agent | After completing work, before delivery | Catch obvious errors early |
| Peer review | Another agent (typically QA) | After delivery, before user acceptance | Independent quality check |
| User review | Human | After delivery | Final acceptance or rejection with feedback |

### Defect Severity

| Severity | Definition | Required Action | SLA |
| --- | --- | --- | --- |
| **Critical** | Output is wrong, breaks functionality, or contradicts requirements | Immediate correction, block delivery until fixed | Same cycle |
| **Major** | Significant gap in completeness or correctness, but not breaking | Correct before acceptance | Next cycle |
| **Minor** | Small inaccuracy, suboptimal approach, or missing polish | Correct if time permits, log for follow-up | Best effort |
| **Cosmetic** | Formatting, naming, style inconsistencies | Bundle with next change | No SLA |

### Correction Scope

- **Isolated fix**: Defect is self-contained; fix does not affect other outputs
- **Cascading fix**: Defect implies other outputs may also be wrong; verify related work
- **Rework**: Fundamental approach is flawed; redo the task from requirements

## Review Procedure

Run this checklist against completed work:

### 1. Requirements Compliance
- [ ] All acceptance criteria from the original request are addressed
- [ ] No requirements were silently dropped or reinterpreted
- [ ] Scope matches what was asked — nothing added, nothing missing

### 2. Correctness
- [ ] Output produces the intended result (code runs, design works, docs are accurate)
- [ ] Edge cases and error conditions are handled appropriately
- [ ] No regressions introduced to existing functionality

### 3. Completeness
- [ ] All files that should have been created or modified were touched
- [ ] No placeholder or TODO items remain unless explicitly agreed
- [ ] Integration points with other components are addressed

### 4. Consistency
- [ ] Output aligns with existing project conventions and patterns
- [ ] Naming, formatting, and style match the codebase
- [ ] No contradictions with other recent outputs

### 5. Quality
- [ ] Solution is appropriately simple (no over-engineering)
- [ ] Code is readable and maintainable
- [ ] Documentation is sufficient but not excessive

## Correction Protocol

When a defect is identified:

1. **Classify** — Assign severity and correction scope using the tables above
2. **Isolate** — Identify the exact location and root cause of the defect
3. **Propose** — Describe the correction before applying it; for major/critical defects, confirm approach with the requester
4. **Apply** — Make the correction
5. **Verify** — Confirm the fix resolves the defect without introducing new issues
6. **Document** — Log the defect type and correction for metrics tracking

## Review-Correction Loop

### Iteration Rules
- **Max cycles**: 3 review-correction iterations per task before escalation
- **Exit criteria**: All critical and major defects resolved; minor defects logged
- **Convergence check**: Each cycle must reduce total defect count; if defects increase or stay flat after 2 cycles, escalate

### Escalation
When corrections are not converging:
1. Summarize the defect pattern and attempted corrections
2. Escalate to the Orchestrator for re-routing (different agent, different approach, or human intervention)
3. Log the escalation in task metrics with `escalation_reason`

## When to Apply

- After task delivery when the user requests changes or reports issues
- During peer review of another agent's output
- When self-reviewing before delivery (complements Accuracy Validation)
- When a task is returned for rework

## When Not to Apply

- Trivial one-line fixes with obvious correctness
- During initial development (use Accuracy Validation instead)
- For feedback that changes requirements rather than correcting output (use Feedback & Learning instead)

## Output
Defect list with severity (critical/major/minor/cosmetic), correction scope, and status (fixed/deferred/escalated). Be concise — table format; omit passing checklist items.

## Integration

- **Accuracy Validation**: This skill extends layers 3-4 (human spot-check and post-hoc monitoring) with a structured correction workflow
- **Performance Metrics**: Log `rework_cycles` count and `defects_found` with severity breakdown on task completion
- **Human Oversight Protocol**: Escalation from this skill feeds into the approval gate system when corrections don't converge
