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

### 3. Verify acceptance criteria (gate)

Before implementation begins, dispatch a spec-compliance-review subagent in **criteria verification mode** (see `prompts/spec-reviewer.md` § Pre-build criteria verification mode). Pass the plan's acceptance criteria and per-step test expectations.

The reviewer evaluates each criterion for:
- **Specificity**: Could two developers independently verify this criterion and agree on pass/fail?
- **Testability**: Can this criterion be validated with a test or observable output?
- **Completeness**: Are edge cases and error conditions addressed?

If any criteria are flagged:
1. Present the findings to the user with the reviewer's suggested improvements
2. Ask: "Revise these criteria before building, or proceed anyway?"
3. If the user overrides, log the override in the build output and continue
4. If the user revises, update the plan file and re-verify

### 4. Implement each step

For each step in the plan, dispatch implementation following the implementer template (`prompts/implementer.md`):

1. **RED** — Write the failing test described in the step. Run the test suite. **Hard gate: the new test must fail.** Paste the failing output. If the test passes without new code, the behavior already exists — pick a different test. Do NOT proceed to GREEN without pasted failing output.
2. **GREEN** — Write the minimum implementation to make the failing test pass. Do not add behavior beyond what the test requires. Run the test suite. **Hard gate: all tests must pass.** Paste the passing output. Do NOT proceed without pasted passing output.
3. **REFACTOR** — Clean up structure, naming, duplication without changing behavior. Run tests again — they must still pass. If tests break, undo and try a smaller change.
4. **Inline review checkpoint** — Route review depth based on the step's **Complexity** classification:
   - **trivial**: Skip inline review. The final `/code-review` (step 6) covers all modified files.
   - **standard**: Run `/review-agent spec-compliance-review` against changed files. If it passes, run quality review agents relevant to what changed. If review finds actionable issues (error/warning with high/medium confidence), auto-fix and re-run failed agents (up to 5 iterations per the review-fix loop in `agents/orchestrator.md`). Escalate to user if the loop doesn't converge.
   - **complex**: Run `/review-agent spec-compliance-review`, then the full quality agent suite including opus-tier agents (security-review, domain-review, arch-review). Same review-fix loop applies.
   - If no complexity is specified, default to **standard**.
   - **UI changes (any complexity)**: After quality review passes, run browser verification via `/browse` in automated smoke test mode. Skip with warning if the dev server is not running. See `agents/orchestrator.md` Stage 3.
5. **Mark step done** — Update the plan file: check off the step's acceptance criteria, set the step as completed.

### 5. Run full test suite

After all steps are complete, run the full test suite. Paste the output as final verification evidence.

### 6. Run code review

Run `/code-review` against all files modified during the build.

### 7. Update plan status

Update the plan status to `implemented`. Briefly confirm completion and direct the user to `/pr`.

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
