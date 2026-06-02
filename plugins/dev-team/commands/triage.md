---
name: triage
description: >-
  Investigate a bug, find its root cause, and file a GitHub issue with a TDD
  fix plan. Use when the user reports a bug and wants it triaged, says "triage
  this", "investigate and file an issue", or wants a hands-off bug investigation
  that produces an actionable issue.
argument-hint: "<bug description or error message>"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write, Agent
---

# Bug Triage

Investigate a bug hands-off, find root cause, and file a GitHub issue with a TDD fix plan.

## Process

### 1. Capture the Problem

Get the bug description from the arguments or conversation. If unclear, ask ONE question: "What's the problem you're seeing?" Then start investigating immediately — minimize questions.

Arguments: $ARGUMENTS

### 2. Investigate

Apply the systematic debugging protocol from `skills/systematic-debugging/SKILL.md`:

1. **Reproduce**: Run the failing test or trigger the error
2. **Investigate**: Trace data flow, check recent changes, find working reference code
3. **Root cause**: Form and test a hypothesis

Use the Agent tool with `subagent_type: "Explore"` to deeply investigate the codebase. Look at:
- Related source files and their dependencies
- Existing tests (what's tested, what's missing)
- Recent changes to affected files (`git log`)
- Error handling in the code path
- Similar patterns elsewhere that work correctly

### 3. Design TDD Fix Plan

Create an ordered list of RED-GREEN cycles, each a vertical slice:

- **RED**: A specific test capturing broken/missing behavior
- **GREEN**: The minimal code change to make that test pass

Tests should verify behavior through public interfaces, not implementation details.

### 4. Create GitHub Issue

Create the issue using `gh issue create`:

```bash
gh issue create --title "<concise bug title>" --body "$(cat <<'EOF'
## Problem

- **Actual behavior**: [what happens]
- **Expected behavior**: [what should happen]
- **Reproduction**: [how to trigger it]

## Root Cause Analysis

[What code path is involved, why it fails, contributing factors.
Describe modules and behaviors, not file paths — the issue should
remain useful after refactors.]

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
EOF
)"
```

### 5. Present Results

Print the issue URL and a one-line root cause summary. Do not repeat the full issue body in chat.
