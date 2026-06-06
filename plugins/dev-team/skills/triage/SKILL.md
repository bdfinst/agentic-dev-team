---
name: triage
description: >-
  Investigate a bug, find its root cause, and write a portable triage record to
  .triage/<slug>.md with a TDD fix plan. Use when the user reports a bug and
  wants it triaged, says "triage this", "investigate and write it up", or wants
  a hands-off bug investigation that produces an actionable record.
argument-hint: "<bug description or error message>"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write, Agent
---

# Bug Triage

Role: worker.

Investigate a bug hands-off, find root cause, and write a TDD fix plan to a
portable triage record at `.triage/<slug>.md` — no issue-tracker dependency.

## Worker constraints

1. Investigate and record; do not fix the bug.
2. Find root cause before recording; do not record on symptoms alone.
3. **Be concise.** The record is structured; chat is the `triage-record:` line
   plus a one-line root-cause summary — not the full body.

## Process

### 1. Capture the Problem

Get the bug description from the arguments or conversation. If no description is
given, ask EXACTLY one question: `What's the problem you're seeing?` and stop.
If a description is given, ask nothing — start investigating immediately.

Arguments: $ARGUMENTS

### 2. Investigate

Apply the systematic debugging protocol from `skills/systematic-debugging/SKILL.md`:

1. **Reproduce**: Run the failing test or trigger the error
2. **Investigate**: Trace data flow, check recent changes, find working reference code
3. **Root cause**: Form and test a hypothesis

Use the Agent tool with `subagent_type: "Explore"` to deeply investigate the codebase:
related source files and dependencies, existing tests (covered vs missing),
recent changes to affected files (`git log`), error handling in the code path,
and similar patterns elsewhere that work correctly.

### 3. Design TDD Fix Plan

Create an ordered list of RED-GREEN cycles, each a vertical slice:

- **RED**: A specific test capturing broken/missing behavior
- **GREEN**: The minimal code change to make that test pass

Tests verify behavior at the public interface, not implementation details.

### 4. Write the Triage Record

**Resolve the slug** from the bug title/description with this 8-step algorithm:

1. Lowercase.
2. Strip non-ASCII characters.
3. Replace spaces and underscores with hyphens.
4. Strip every character that is not `[a-z0-9-]`.
5. Collapse consecutive hyphens to one.
6. If longer than 60 characters, truncate to 60, then cut back to the last
   hyphen (so no word is split).
7. Strip leading/trailing hyphens.
8. If the result is empty, fall back to `triage-YYYYMMDD` (today's UTC date).

**Resolve collisions:** if `.triage/<slug>.md` exists, append `-2`, `-3`, … up
to `-99` until a free name is found. **Never overwrite** an existing record.

**Write the file:**

```bash
mkdir -p .triage/
```

If `.triage/` cannot be created or written (permission/read-only): report
`Cannot write .triage/<slug>.md: <error>`, write the same content to a temp file
(`tmp/triage-<slug>.md` or `$TMPDIR`), and print the full record content to chat
so nothing is lost.

The record is YAML frontmatter followed by four sections:

```markdown
---
id: <resolved-slug>
created: <YYYY-MM-DDThh:mm:ssZ>
status: open
---

# <concise bug title>

## Problem

- **Actual behavior**: [what happens]
- **Expected behavior**: [what should happen]
- **Reproduction**: [how to trigger it]

## Root Cause Analysis

[What code path is involved, why it fails, contributing factors. Describe
modules and behaviors, not file paths — the record should survive refactors.]

## TDD Fix Plan

1. **RED**: Write a test that [expected behavior]
   **GREEN**: [Minimal change to pass]

2. **RED**: Write a test that [next behavior]
   **GREEN**: [Minimal change to pass]

**REFACTOR**: [Any cleanup after all tests pass]

## Acceptance Criteria

- [ ] Root cause is addressed (not just symptom)
- [ ] All new tests pass
- [ ] Existing tests still pass
- [ ] No regressions introduced
```

At least one RED/GREEN cycle is required. **If no root cause was determined,**
the entire `## TDD Fix Plan` body is exactly:

```
Root cause not determined — manual investigation required
```

### 5. Present Results

Print exactly two lines:

1. `triage-record: .triage/<resolved-slug>.md` (the actual resolved path)
2. A root-cause summary of at most 120 characters.

Do not repeat the full record body in chat.
