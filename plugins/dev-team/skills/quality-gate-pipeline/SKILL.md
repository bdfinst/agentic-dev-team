---
name: quality-gate-pipeline
description: Unified quality gate for agent output — self-validation, verification evidence, and review-correction loops. Consolidates accuracy-validation, verification-before-completion, and task-review-correction into a single three-phase pipeline. Use before delivery, at completion, and during rework.
role: worker
user-invocable: true
---

# Quality Gate Pipeline

## Overview

Single quality gate that every agent passes through before output is accepted. Replaces three formerly separate skills (accuracy-validation, verification-before-completion, task-review-correction) with a unified pipeline of three phases that run in sequence.

## Constraints

- Do not deliver output containing unverified claims; pause and verify first
- Do not claim completion without fresh verification evidence from this session
- Do not reference test results or tool output from earlier in the conversation — re-run and show current output
- Do not substitute reasoning or explanation for actual evidence
- Max 3 review-correction cycles before escalating to the Orchestrator
- Each correction cycle must reduce total defect count; flat or increasing defects trigger escalation

## The Three Phases

### Phase 1: Self-Validation (before delivery)

Every agent runs this checklist mentally before presenting output.

**Factual Accuracy**

- [ ] All file paths referenced actually exist (verify with tool, don't assume)
- [ ] All function/class/variable names match what's in the codebase
- [ ] Version numbers, API signatures, and config values are verified, not recalled from training
- [ ] No statistics or citations are fabricated
- [ ] Claims about an external tool or product's UI (menu paths, button/control labels, screen layouts, settings locations) are backed by a citation the agent actually has — a fetched doc, a user-provided screenshot/description, or tool output — not recalled from training as if current and authoritative. When no citation exists, say so plainly (e.g. "I don't have a verified/current view of this menu — check the tool's current UI") rather than describing specifics; this is the same **Low** confidence fallback as any other recalled/guessed claim (see Confidence Assessment below).

**Instruction Fidelity**

- [ ] Output addresses what the user actually asked, not a reinterpretation
- [ ] All acceptance criteria from the task are met
- [ ] No scope creep beyond the request
- [ ] Constraints from the agent persona are respected

**Internal Consistency**

- [ ] No contradictions within the output
- [ ] Code samples compile/run conceptually (correct syntax, valid imports)
- [ ] Referenced earlier decisions are accurately recalled (if unsure, re-read from .claude/memory/)

**Confidence Assessment**

| Confidence | Meaning | Action |
| --- | --- | --- |
| **High** | Verified via tool output or direct file read | Deliver as-is |
| **Medium** | Inferred from context, not directly verified | Flag with caveat |
| **Low** | Recalled from training or guessed | Verify before delivering, or mark as unverified |

**Hallucination Detection Signals**

Strong signals (likely hallucination):

- Referencing a file, function, or API that was never read in this session
- Quoting specific numbers without a source
- Describing behavior that contradicts tool observations
- Generating imports for packages not in dependencies
- Describing a specific control, menu path, or screen in an external tool/product without a citation the agent can point to

When a signal fires: **Pause** → **Verify** (use tools) → **Correct** → **Log** (`hallucination_detected: true` in metrics)

### Phase 2: Verification Evidence (before completion claims)

**Iron Law**: No completion claims without fresh verification evidence. Skipping any step is falsification, not verification.

**The Gate Function**:

1. **IDENTIFY** — What command proves your claim? (e.g., `npm test`, `cargo build`)
2. **RUN** — Execute the command fresh and completely. Not from cache, not from memory.
3. **READ** — Read the complete output and exit code. Don't skim.
4. **VERIFY** — Does the output actually confirm your claim? If not, report actual status.
5. **ONLY THEN** — Make the claim, with supporting evidence pasted.

**Required Evidence (all tasks)**:

1. **Tests pass**: Run the **whole** test suite. Paste output with pass/fail counts.
2. **Build succeeds**: If the project has a build step, run it. Paste output.
3. **Lint clean**: If the project has a linter, run it. Paste output.
4. **No regressions**: Test count should not decrease.
5. **Coverage & Mutation (necessary-not-sufficient)**: Coverage thresholds and mutation score gate entry but do not alone gate exit. Saturating at 100% line coverage and 1.0 mutation score on small slices is expected and does not indicate structural quality. They are required to pass but are not the final signal.
6. **Structural Quality gate**: Before claiming "done", the work must carry a clean-or-triaged `structure-review` + `complexity-review` signal. Options:
   - **Clean**: Both agents produced no `error`/`warning` findings on the latest diff.
   - **Triaged**: Every `error`/`warning` finding is logged as a deferred item (with owner + tracking reference) per the Phase 3 exit criteria — and surfaced in the completion summary.
   - **Waiver**: For hotfixes, documentation-only changes, or work pre-approved by the Orchestrator as out-of-scope for structural review, include a waiver statement: `structural-review-waiver: <reason>` in the completion summary. Waivers are surfaced, not hidden.

**Quality Ownership**: green means the **entire suite**, not just the tests your
change touched. A failing test is a failing test **regardless of whether this change
caused it** — "already broken" / "not my diff" is not a pass. A red signal you
observe must be **fixed**, or **explicitly surfaced and triaged** (file an issue, or
record a quarantine with a reason via `/triage`) and reported as **not green**.
Never claim completion over a red suite by attributing the failure to someone else's
change. You own the quality state you can see, not just your delta.

**Additional Evidence by task type**:

| Task Type | Additional Evidence |
| ----------- | ------------------- |
| Bug fix | Red-green cycle: failing test → passing test |
| New feature | Feature working via test output or demo command |
| Refactor | Same test count, same pass count |
| Config change | Config loads without error |
| Documentation | Commands/code blocks in doc actually work |
| Agent work | Inspect VCS diff independently — don't trust self-report |

**Evidence Format**:

```
## Verification
- Tests: `npm test` → 47 passed, 0 failed (output below)
- Build: `npm run build` → success, 0 warnings
- Lint: `npm run lint` → 0 errors, 0 warnings
```

**Red Flag Language** — stop and verify when you catch yourself saying:

- "should work now" / "should be fixed" / "probably" / "I believe"
- Expressing satisfaction before running verification
- Preparing commits without verification output

### Phase 3: Review-Correction Loop (post-delivery rework)

Activated when output is returned for rework, during peer review, or when self-reviewing before delivery (complements Phase 1).

**Defect Severity**:

| Severity | Definition | Required Action |
| --- | --- | --- |
| **Critical** | Wrong, breaks functionality, contradicts requirements | Immediate correction, block delivery |
| **Major** | Significant gap in completeness or correctness | Correct before acceptance |
| **Minor** | Small inaccuracy, suboptimal approach | Correct if time permits |
| **Cosmetic** | Formatting, naming, style | Bundle with next change |

**Correction Scope**:

- **Isolated fix**: Self-contained; fix doesn't affect other outputs
- **Cascading fix**: Implies other outputs may also be wrong; verify related work
- **Rework**: Fundamental approach flawed; redo from requirements

**Review Checklist**:

1. Requirements compliance — all acceptance criteria addressed, no silent scope changes
2. Correctness — intended result, edge cases handled, no regressions
3. Completeness — all files touched, no TODOs remain, integration points addressed
4. Consistency — matches project conventions, no contradictions
5. Quality — appropriately simple, readable, sufficient documentation

**Iteration Rules**:

- Max 3 review-correction cycles before escalation
- Each cycle must reduce total defect count
- If defects increase or stay flat after 2 cycles, escalate to Orchestrator
- Exit criteria: all critical and major defects **resolved** (fixed and re-verified). Minor defects may be **deferred** — but deferred ≠ resolved: each must be logged with an owner and a tracking reference and **surfaced in the completion summary**, never folded into "done." A slice carrying deferred items is "complete with known follow-ups," not silently "complete."

**Escalation**: Summarize defect pattern and attempted corrections → escalate to Orchestrator for re-routing → log with `escalation_reason` in task metrics.

## When to Apply Each Phase

| Situation | Phases to run |
| ----------- | -------------- |
| Initial development, about to deliver | Phase 1 → Phase 2 |
| Claiming task completion | Phase 2 (at minimum) |
| Output returned for rework | Phase 3 → Phase 2 |
| Peer-reviewing another agent's output | Phase 1 (as reviewer) → Phase 3 if defects found |
| Trivial one-line fix | Phase 2 only (verify it works) |

## Output

Phase 1: Confidence-scored validation — report failures only.
Phase 2: Verification evidence block with tool output.
Phase 3: Defect table (severity, scope, status: fixed/deferred/escalated).

## Integration

- **Performance Metrics**: `hallucination_detected`, `rework_cycles`, `defects_found` are logged automatically by `hooks/task_completion_metrics.py` on task completion — no skill-level logging step needed. To surface non-default values, populate `.claude/session-metrics.json` with the relevant fields before the session ends.
- **Context Summarization**: When context is high, increase Phase 1 rigor
- **Human Oversight Protocol**: Escalation from Phase 3 feeds into the approval gate system
