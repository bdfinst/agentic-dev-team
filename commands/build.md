---
name: build
description: >-
  Execute an approved implementation plan using TDD. Reads the plan, implements
  each step with RED-GREEN-REFACTOR, runs inline review checkpoints, and
  produces verification evidence. Use when the user says "build this", "implement
  the plan", "start building", or after /plan has been approved.
argument-hint: "[--plan <path>]"
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent, AskUserQuestion
---

# Build

Role: orchestrator. This command implements an approved plan — it does not create plans or specs.

You have been invoked with the `/build` command.

## Orchestrator constraints

1. **Follow the plan exactly.** If the plan is wrong, stop and ask the user — do not deviate silently.
2. **Every step must be TDD.** Each step follows RED → GREEN → REFACTOR. No implementation without a failing test first.
3. **Incremental.** Each step must leave the codebase in a working, committable state.
4. **Verification evidence required.** Paste fresh test output before claiming a step is done.
5. **Review checkpoints.** After each unit of work, run inline review (spec-compliance first, then quality agents). Max 2 correction iterations before escalating.

## Parse Arguments

Arguments: $ARGUMENTS

- `--plan <path>`: Path to the plan file. If omitted, search `plans/` for the most recently modified plan with status `approved`.

## Steps

### 1. Find the plan

If `--plan` was provided, read that file. Otherwise, search `plans/` for `.md` files and find the most recently modified one with `**Status**: approved`. If no approved plan is found, tell the user: "No approved plan found. Run `/plan` first, then approve it."

### 2. Verify plan status

Read the plan file. If the status is not `approved`, ask the user: "This plan has status '<status>'. Approve it before building, or continue anyway?"

### 3. Implement each step

For each step in the plan, dispatch implementation following the implementer template (`prompts/implementer.md`):

1. **RED** — Write the failing test described in the step. Run it. Confirm it fails for the expected reason. Paste the output.
2. **GREEN** — Write the minimum implementation to pass. Run the test. Confirm it passes. Paste the output.
3. **REFACTOR** — Clean up if the plan specifies refactoring for this step. Run tests again.
4. **Inline review checkpoint** — Run `/review-agent spec-compliance-review` against changed files. If it passes, run quality review agents relevant to what changed. If review fails, apply corrections (max 2 iterations). If still failing after 2, escalate to the user.
5. **Mark step done** — Update the plan file: check off the step's acceptance criteria, set the step as completed.

### 4. Run full test suite

After all steps are complete, run the full test suite. Paste the output as final verification evidence.

### 5. Run code review

Run `/code-review --changed` against all files modified during the build.

### 6. Update plan status

Set the plan status to `implemented`. Report a summary:
- Steps completed
- Tests added/modified
- Files changed
- Review findings (if any)
- Any deviations from the plan (with justification)

Ask the user: "Build complete. Run `/pr` to create a pull request, or review the changes first?"

## Escalation

Stop and ask the user when:
- A test fails for an unexpected reason after 3 attempts
- The plan requires architectural decisions not covered by the plan
- A review checkpoint fails after 2 correction iterations
- You discover the plan is incomplete or contradictory

## Integration

- `/specs` produces the specification artifacts that inform the plan
- `/plan` creates the plan this command executes
- `/code-review` runs the full review suite after implementation
- `/pr` creates the pull request after a successful build
- `/continue` can resume a partially completed build across sessions
- The progress-guardian agent tracks step completion against the plan
