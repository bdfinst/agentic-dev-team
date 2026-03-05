---
name: accuracy-validation
description: Apply before delivering any output. Detects hallucinations, scores output confidence, and triggers corrections. Use whenever an agent is about to deliver a response and wants to verify factual accuracy, or when reviewing another agent's output for quality.
role: worker
user-invocable: true
---

# Accuracy Validation

## Overview

Procedures for detecting hallucinations, scoring output confidence, and triggering corrections. Every agent applies self-validation before delivering output. The QA agent performs secondary validation when applicable.

## Constraints
- Do not deliver output containing unverified claims; pause and verify first
- Do not guess at file paths, function names, or API signatures — use tools to confirm
- Escalate rather than fabricate when a claim cannot be verified
- Apply self-validation to your own output before delivery, not only to others'

## Multi-Layer Validation

Validation happens at four layers, each catching different failure modes:

| Layer | Who | When | What |
| --- | --- | --- | --- |
| 1. Self-validation | Active agent | Before delivering any output | Check own output against known facts and instructions |
| 2. Peer validation | QA agent or reviewing agent | After primary output, before delivery | Cross-check for consistency and correctness |
| 3. Human spot-check | User | After delivery | Review and accept/reject/amend |
| 4. Post-hoc monitoring | Orchestrator | During learning loop | Identify patterns in rejections and corrections |

## Self-Validation Checklist

Every agent runs this checklist mentally before presenting output:

### Factual Accuracy
- [ ] All file paths referenced actually exist (verify with tool, don't assume)
- [ ] All function/class/variable names match what's in the codebase
- [ ] Version numbers, API signatures, and config values are verified, not recalled from training
- [ ] No statistics or citations are fabricated

### Instruction Fidelity
- [ ] Output addresses what the user actually asked, not a reinterpretation
- [ ] All acceptance criteria from the task are met
- [ ] No scope creep beyond the request
- [ ] Constraints from the agent persona are respected

### Internal Consistency
- [ ] No contradictions within the output
- [ ] Code samples compile/run conceptually (correct syntax, valid imports)
- [ ] Referenced earlier decisions are accurately recalled (if unsure, re-read from memory/)

### Confidence Assessment
Rate confidence for each major claim or output component:

| Confidence | Meaning | Action |
| --- | --- | --- |
| **High** | Verified via tool output or direct file read | Deliver as-is |
| **Medium** | Inferred from context, not directly verified | Flag with caveat: "Based on [assumption], this should..." |
| **Low** | Recalled from training or guessed | Verify before delivering, or explicitly mark as unverified |

## Hallucination Detection Signals

Watch for these indicators that output may contain hallucinations:

### Strong Signals (likely hallucination)
- Referencing a file, function, or API that was never read in this session
- Quoting specific numbers (metrics, versions, dates) without a source
- Describing system behavior that contradicts what was observed via tools
- Generating import statements for packages not in the project's dependencies

### Weak Signals (investigate further)
- Unusually confident language about details not recently verified
- Output that "feels right" but wasn't derived from tool output
- Filling in gaps in requirements with plausible but unconfirmed details
- Describing error messages or stack traces from memory rather than tool output

### When a Signal Fires
1. **Pause** - do not deliver the suspect output
2. **Verify** - use tools (Read, Grep, Bash) to check the claim
3. **Correct** - fix if wrong, or flag uncertainty if unverifiable
4. **Log** - mark `hallucination_detected: true` in the task metrics if a correction was needed

## Correction Triggers

### Automatic Correction
Apply immediately without user approval:
- Syntax errors in generated code
- Incorrect file paths (verified via Glob/Read)
- Mismatched variable/function names (verified via Grep)

### User-Confirmed Correction
Present the issue and proposed fix to the user:
- Logical errors in business logic
- Ambiguous requirement interpretations
- Design decisions that could go either way

### Escalation
Flag to the user with full context:
- Multiple hallucination signals firing on the same output
- Low confidence on a critical deliverable
- Contradictory information from different sources

## Output
Confidence-scored validation result: list of checklist items that failed, hallucination signals identified, and required corrections with their trigger type (automatic/user-confirmed/escalation). Be concise — report failures only; omit passing items.

## Integration with Other Skills

- **Performance Metrics**: Log `hallucination_detected` flag on task completion entries
- **Context Summarization**: When context is high, increase validation rigor (more tool-based verification)
- **Human Oversight Protocol**: Hallucination escalation feeds into the approval gate system
