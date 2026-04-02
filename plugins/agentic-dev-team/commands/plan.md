---
name: plan
description: >-
  Create a structured implementation plan with goal, acceptance criteria,
  incremental TDD steps, and a pre-PR quality gate. Use this for tasks that
  need a plan but not the full three-phase orchestration, or when the user
  says "plan this", "make a plan", "break this down", or "how should I
  implement this".
argument-hint: "<task-description> [--output <path>]"
user-invocable: true
allowed-tools: Read, Write, Glob, Grep, Bash(mkdir *), Bash(date *), Bash(git branch *), AskUserQuestion
---

# Plan

Role: orchestrator. This command creates a structured plan — it does not implement anything.

You have been invoked with the `/plan` command.

## Orchestrator constraints

1. **Do not implement.** Produce only the plan. No code, no scaffolding, no file edits beyond the plan file itself.
2. **Every step must be TDD.** Each step follows RED → GREEN → REFACTOR.
3. **Incremental.** Each step must leave the codebase in a working, committable state.
4. **Human approval required.** Present the plan for approval before any implementation begins.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: task description (required)
- `--output <path>`: Write plan to a specific path. Default: `plans/<slugified-task>.md`

## Steps

### 1. Check for spec artifacts

Search for specification artifacts produced by `/specs` — look for files matching `docs/specs/**`, `specs/**`, or `*.feature` files related to the task. Check for the four artifacts: Intent Description, User-Facing Behavior (Gherkin), Architecture Specification, and Acceptance Criteria.

If no spec artifacts are found, ask the user: "No specification artifacts found for this task. Run `/specs` first to produce them, or continue planning without specs?"

If the user chooses to continue without specs, proceed. Otherwise, stop and let them run `/specs` first.

### 2. Understand the task

Read relevant code and context to understand what needs to change. Keep exploration focused — this is planning, not research. If the task is complex enough to need deep research, suggest `/design-doc` instead. If spec artifacts exist, use them as the primary source for acceptance criteria and scope.

### 3. Create the plan

Write the plan file using this structure:

```markdown
# Plan: <Task Title>

**Created**: <date>
**Branch**: <current branch>
**Status**: draft

## Goal

<One paragraph describing what this plan achieves and why.>

## Acceptance Criteria

- [ ] <Criterion 1 — observable, testable>
- [ ] <Criterion 2>
- [ ] <Criterion 3>

## Steps

### Step 1: <Description>

**Complexity**: <trivial | standard | complex>
**RED**: Write test for <behavior>
**GREEN**: Implement <minimal code to pass>
**REFACTOR**: <What to clean up, or "None needed">
**Files**: `path/to/file.ts`, `path/to/file.test.ts`
**Commit**: `<draft commit message>`

### Step 2: <Description>

...

## Complexity Classification

Each step must include a complexity rating that controls review depth during `/build`:

| Rating | Criteria | Review depth |
|--------|----------|--------------|
| `trivial` | Single-file rename, config change, typo fix, documentation-only | Skip inline review; covered by final `/code-review --changed` |
| `standard` | New function, test, module, or behavioral change within existing patterns | Spec-compliance + relevant quality agents |
| `complex` | Architectural change, security-sensitive, cross-cutting concern, new abstraction | Full agent suite including opus-tier agents |

When in doubt, classify up (standard rather than trivial, complex rather than standard).

## Pre-PR Quality Gate

- [ ] All tests pass
- [ ] Type check passes (if applicable)
- [ ] Linter passes
- [ ] `/code-review --changed` passes
- [ ] Documentation updated (if applicable)

## Risks & Open Questions

- <Risk or question, with mitigation or who should answer>
```

### 4. Create the plans directory

Create `plans/` if it doesn't exist.

### 5. Present for approval

Display the plan and ask: "Approve this plan to begin implementation, or suggest changes?"

Mark the plan status as `approved` once the user confirms. If the user requests changes, update the plan and re-present.

## Integration

- The progress-guardian agent tracks step completion against this plan
- `/continue` reads active plans to resume work
- The orchestrator's Phase 2 produces plans in this same format for larger tasks
