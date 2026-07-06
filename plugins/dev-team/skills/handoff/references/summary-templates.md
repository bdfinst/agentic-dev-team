# Summary & Progress File Templates

These templates structure output written by the `handoff` skill — continue-mode
templates go to `memory/`; fork-mode templates go to the OS temp dir.

- **Task Summary** -- general-purpose summary for any completed or paused task (continue mode).
- **Research Progress File** -- output of the Research phase; onboards the Planner (continue mode).
- **Plan Progress File** -- output of the Plan phase; onboards the Implementer (continue mode).
- **Implementation Progress File** -- mid-phase compaction during long implementations (continue mode).
- **Fork Handoff** -- artifact for splitting off an out-of-scope side-task to an independent session (fork mode).
- **Fork Hand-Back** -- artifact a forked session writes when reporting results back to its parent (fork mode).

---

## Task Summary

**File naming**: `memory/{date}-{task-slug}.md` (e.g., `memory/2026-02-20-user-auth-api.md`)

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

Be concise in summaries -- preserve decisions and artifacts, discard process narration.

---

## Research Progress File

```markdown
# Research: [Brief Description]

## Date
[ISO date]

## Task
[1-2 sentence description of what was requested]

## System Understanding
- [How the relevant part of the system works -- data flows, dependencies, key abstractions]

## Files Involved
- `path/to/file.ext:L42-L78` -- [what this section does and why it matters]
- `path/to/other.ext:L15` -- [what this line/function does]

## Key Findings
- [Finding 1]: [Evidence and location]
- [Finding 2]: [Evidence and location]

## Constraints & Gotchas
- [Constraint or non-obvious behavior that the planner must account for]

## Open Questions
- [Anything unresolved that needs human input or further investigation]
```

---

## Plan Progress File

```markdown
# Plan: [Brief Description]

## Date
[ISO date]

## Task
[1-2 sentence description of what was requested]

## Changes

### 1. [Change description]
- **File**: `path/to/file.ext`
- **What**: [Specific change -- add function, modify logic, update config]
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
1. [First change -- why it must come first]
2. [Second change -- depends on first because...]
3. [Verification step]

## Decisions Made
- [Decision]: [Rationale, alternatives considered]

## Status
- [ ] Change 1
- [ ] Change 2
- [ ] All tests passing
```

---

## Implementation Progress File (Mid-Phase Compaction)

```markdown
# Implementation Progress: [Brief Description]

## Date
[ISO date]

## Completed
- [x] Change 1: `path/to/file.ext` -- [what was done]
- [x] Change 2: `path/to/file.ext` -- [what was done]

## In Progress
- [ ] Change 3: `path/to/file.ext` -- [current state, what remains]

## Remaining
- [ ] Change 4: [from the plan]
- [ ] Final verification

## Issues Encountered
- [Issue]: [How it was resolved, or if still open]

## Test Results
- [Which tests pass, which fail, what needs attention]
```

---

## Fork Handoff

**File naming**: `{tmpdir}/handoff-{purpose-slug}-{date}.md` (e.g.,
`/tmp/handoff-flaky-test-repro-2026-07-06.md`) — never `memory/`.

```markdown
# Fork Handoff: [Stated Purpose]

## Date
[ISO date]

## Purpose
[The one-line stated purpose this fork exists for — required, not inferred]

## Scope (Just This Slice)
[Only the context relevant to the stated purpose -- not the full parent session]

## Pointers, Not Duplication
- [Existing artifact/file/doc]: [what it already covers -- link or cite, don't copy]
- [Existing artifact/file/doc]: [what it already covers -- link or cite, don't copy]

## Suggested Skills
- [Skill]: [why the receiving session likely needs it loaded]

## Key Context to Start
- [Anything the receiving session needs to begin without replaying the parent's history]

## Hand-Back Expected
- [ ] Yes -- see Fork Hand-Back template; delete this file once the hand-back is read
- [ ] No -- this is a one-way split; delete this file once the receiving session confirms it has consumed it
```

Redact secrets, API keys, tokens, and PII before writing -- this file lives outside the repo's trust boundary.

**Cleanup**: event-based only. Delete on consumption (receiving session merges its result back, or the parent reads the hand-back). Never sweep on a schedule.

---

## Fork Hand-Back

Written by the forked/child session when it reports results back to its parent.

**File naming**: `{tmpdir}/handoff-{purpose-slug}-handback-{date}.md`

```markdown
# Fork Hand-Back: [Stated Purpose]

## Date
[ISO date]

## Result Summary
[1-3 sentences: what the fork accomplished]

## Changes / Findings
- [File path or artifact]: [what changed and why, or what was found]

## Merge Guidance
[What the parent session should do with this -- apply a diff, adopt a decision,
just note a finding -- in a shape the parent can act on without replaying the
fork's history]

## Open Items
[Anything unresolved that the parent still needs to decide or follow up on]
```

Redact secrets, API keys, tokens, and PII before writing.

**Cleanup**: delete this file once the parent session has read it and merged/noted the result -- never time-based.
