---
name: issues-from-plan
description: >-
  Break a plan into independently-grabbable GitHub issues. Use when the user
  says "create issues from this plan", "break this into tickets", "file issues",
  or wants to distribute plan steps across a team.
argument-hint: "[plan file path]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write
---

# Issues from Plan

Break an implementation plan into GitHub issues that can be worked independently.

## Process

### 1. Find the Plan

If a path is provided in arguments, read that file. Otherwise, look for the most recent plan in:
- Active plan in conversation context
- `memory/` directory (phase progress files)
- `plans/` directory

Arguments: $ARGUMENTS

If no plan is found, ask the user to point you to one.

### 2. Analyze the Plan

Read the plan and identify:
- Each discrete unit of work (implementation step, vertical slice, or phase)
- Dependencies between units (which must complete before others can start)
- Acceptance criteria for each unit
- Shared architectural decisions that apply across all issues

### 3. Draft Issues

For each unit of work, draft an issue with:

- **Title**: Short, action-oriented (e.g., "Add user authentication endpoint")
- **Body**:
  - What to build (behavior description, not implementation details)
  - Acceptance criteria as checkboxes
  - Dependencies on other issues (by title reference)
  - Relevant architectural decisions from the plan
  - Testing approach
- **Labels**: suggest appropriate labels if the repo uses them

### 4. Review with User

Present the issue list as a numbered summary:

```
1. [Title] — [one-line description] (depends on: none)
2. [Title] — [one-line description] (depends on: #1)
3. [Title] — [one-line description] (depends on: #1)
...
```

Ask: "Does this breakdown look right? Should any issues be merged or split?"

Wait for approval before creating.

### 5. Create Issues

Create each issue using `gh issue create`. After creating all issues, update issue bodies to cross-reference actual issue numbers for dependencies.

```bash
gh issue create --title "Issue title" --body "$(cat <<'EOF'
## What to Build

[Behavior description — what this slice delivers end-to-end]

## Depends On

- #<number>: [brief reason]

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] All tests pass

## Architectural Context

[Relevant decisions from the plan that apply to this issue]

## Testing Approach

[What to test and how — behavior-level, not implementation-level]
EOF
)"
```

### 6. Present Results

List all created issue URLs with their titles. Note the dependency graph.
