---
name: context-summarization
description: Compress conversation history to maintain context utilization below 40% using LSTM-inspired gates
role: orchestrator
user-invocable: true
---

# Context Summarization

## Overview

Procedure for compressing conversation history to maintain context utilization below 40%. Uses an LSTM-inspired approach with forget/input/output gates to decide what to keep, compress, and discard.

## Constraints
- Summaries replace conversation history; do not reload prior turns from memory
- Never include credentials, PII, or sensitive data in `memory/` summary files
- Summaries must be sufficient for the next phase to start without replaying history
- Archive summaries older than 30 days; delete after 90 days

## When to Summarize

### Triggers

| Utilization | State | Action |
| --- | --- | --- |
| < 30% | Normal | No action needed |
| 30-40% | Warning | Prepare: identify summarization candidates |
| 40-50% | Active | Summarize older conversation turns, keep recent 3-5 turns verbatim |
| 50-65% | Aggressive | Summarize everything except current task, compress skill/agent content |
| 65%+ | Critical | Write full summary to `memory/`, start new conversation |

### Measuring Utilization

**Primary method**: Use the `usage` field from the API response. It reports `input_tokens` and `output_tokens` for each turn. Calculate:

```
utilization = (input_tokens + output_tokens) / model_context_window
```

For Claude (200K window): `utilization = total_tokens / 200000`

**Fallback proxy signals** (when API usage data is not available):

1. **Turn count**: Each turn (user + assistant) averages 500-2,000 tokens. After ~40 turns on a 200K model, you're approaching 40%.
2. **File reads accumulating**: Each file read adds its full content to context. Track how many files have been read.
3. **Code output volume**: Large code generations consume significant context.
4. **Degraded output quality**: If responses become less precise, miss earlier instructions, or repeat themselves, context pressure is likely the cause.

## How to Summarize

### The Three Gates

Apply these in order to every piece of context older than the last 3-5 turns:

#### 1. Forget Gate - What Can Be Discarded?
Remove from active consideration:
- Exploratory dead ends (approaches that were tried and rejected)
- Verbose tool outputs where only the conclusion matters (e.g., full file reads where only 3 lines were relevant)
- Superseded decisions (earlier approach replaced by a later one)
- Debugging steps that led to a resolved issue

#### 2. Input Gate - What New Information Is Essential?
Always preserve:
- Current task definition and acceptance criteria
- Active architectural decisions and their rationale
- Unresolved questions or blockers
- File paths and line numbers currently being worked on
- User preferences and feedback from this session

#### 3. Output Gate - What Must Stay Verbatim for the Current Task?
Keep uncompressed:
- The last 3-5 conversation turns
- Code that is actively being modified
- Error messages being debugged
- The current agent's persona (if loaded)
- The current skill's guidelines (if loaded)

## Summary Format

When writing a summary to `memory/`, use this structure:

### File Naming
```
memory/{date}-{task-slug}.md
```
Example: `memory/2026-02-20-user-auth-api.md`

### Template

```markdown
# Task Summary: [Brief Description]

## Date
[ISO date]

## Task
[1-2 sentence description of what was requested]

## Decisions Made
- [Decision]: [Rationale]
- [Decision]: [Rationale]

## Artifacts Produced
- [File path]: [What was created/modified and why]
- [File path]: [What was created/modified and why]

## Current State
- [What is complete]
- [What is in progress]
- [What is blocked or deferred]

## Key Context for Continuation
- [Anything the next conversation needs to know to pick up where this left off]
- [Unresolved questions]
- [Active constraints or requirements]

## Agents Used
- [Agent]: [What they contributed]

## Skills Applied
- [Skill]: [How it was applied]
```

Be concise in summaries — preserve decisions and artifacts, discard process narration.

## Phase Progress File Templates

These templates are optimized for agent onboarding — the next phase's agent should be able to start working immediately from this file alone, without replaying any conversation history.

### Research Progress File

```markdown
# Research: [Brief Description]

## Date
[ISO date]

## Task
[1-2 sentence description of what was requested]

## System Understanding
- [How the relevant part of the system works — data flows, dependencies, key abstractions]

## Files Involved
- `path/to/file.ext:L42-L78` — [what this section does and why it matters]
- `path/to/other.ext:L15` — [what this line/function does]

## Key Findings
- [Finding 1]: [Evidence and location]
- [Finding 2]: [Evidence and location]

## Constraints & Gotchas
- [Constraint or non-obvious behavior that the planner must account for]

## Open Questions
- [Anything unresolved that needs human input or further investigation]
```

### Plan Progress File

```markdown
# Plan: [Brief Description]

## Date
[ISO date]

## Task
[1-2 sentence description of what was requested]

## Changes

### 1. [Change description]
- **File**: `path/to/file.ext`
- **What**: [Specific change — add function, modify logic, update config]
- **Snippet**: [Key code or pseudocode showing the change]
- **Test**: [How to verify this change works]

### 2. [Change description]
- **File**: `path/to/file.ext`
- **What**: [Specific change]
- **Snippet**: [Key code or pseudocode]
- **Test**: [How to verify]

## Test Strategy
- [Unit tests to add/modify]
- [Integration tests]
- [Acceptance criteria from spec]

## Execution Order
1. [First change — why it must come first]
2. [Second change — depends on first because...]
3. [Verification step]

## Decisions Made
- [Decision]: [Rationale, alternatives considered]

## Status
- [ ] Change 1
- [ ] Change 2
- [ ] All tests passing
```

### Implementation Progress File (Mid-Phase Compaction)

```markdown
# Implementation Progress: [Brief Description]

## Date
[ISO date]

## Completed
- [x] Change 1: `path/to/file.ext` — [what was done]
- [x] Change 2: `path/to/file.ext` — [what was done]

## In Progress
- [ ] Change 3: `path/to/file.ext` — [current state, what remains]

## Remaining
- [ ] Change 4: [from the plan]
- [ ] Final verification

## Issues Encountered
- [Issue]: [How it was resolved, or if still open]

## Test Results
- [Which tests pass, which fail, what needs attention]
```

## Using Summaries in New Conversations

When starting a new conversation that continues previous work:

1. The Orchestrator reads the most recent summary from `memory/`
2. Load only the **Key Context for Continuation** section into active context
3. Load referenced files on demand, not upfront
4. Do NOT reload the full conversation history - the summary replaces it

### Reading Previous Summaries
```
Read .claude/memory/2026-02-20-user-auth-api.md
```

Use the summary to orient, then proceed. If specific details are needed from an artifact, read the artifact file directly rather than trying to reconstruct conversation history.

## In-Conversation Compression

When summarization is needed mid-conversation (40-50% utilization) but a new conversation isn't warranted:

1. Mentally partition the conversation into phases
2. For completed phases, retain only:
   - What was decided
   - What was produced (file paths)
   - What constraints carry forward
3. Let go of:
   - How the decision was reached
   - Intermediate drafts
   - Tool output details

This isn't a literal operation (you can't delete context mid-conversation), but it guides what to reference and build on vs. what to treat as background noise.

## Cleanup

Summaries in `memory/` accumulate over time. Periodically:

1. Archive summaries older than 30 days to `memory/archive/`
2. Delete archived summaries older than 90 days
3. If multiple summaries exist for the same task, consolidate into one
