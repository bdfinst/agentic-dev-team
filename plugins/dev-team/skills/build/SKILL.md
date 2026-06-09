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
6. **Be concise.** Report step status and verification evidence, no narration.

## Parse Arguments

Arguments: $ARGUMENTS

- `--plan <path>`: Path to the plan file. If omitted, search `plans/` for the most recently modified plan with status `approved`.

## Steps

### 1. Find the plan

If `--plan` was provided, read that file. Otherwise, search `plans/` for `.md` files and find the most recently modified one with `**Status**: approved`. If no approved plan is found, tell the user: "No approved plan found. Run `/plan` first, then approve it."

### 1.5. JS project bootstrap gate

Before any TDD step runs, make sure a JS-flavored plan has a project to build in. A fresh JS project with no `package.json` will fail the first RED step (no test runner, no scripts), so bootstrap it first.

1. **Check for `package.json`** in the working directory. If it exists, **skip this gate silently** and continue to Step 2.
2. **Check the plan file for JS/TS signals** — any of `.js`, `.mjs`, `.ts`, `.jsx`, `.tsx`, `node`, `npm`, `vitest`, `jest`, `eslint`. If none are present, the plan is non-JS: **skip this gate silently** and continue to Step 2.
3. **Bootstrap** (only when `package.json` is absent **and** the plan is JS-flavored): print exactly one line — `No package.json found for a JS plan — bootstrapping with js-project-init.` — then invoke the `js-project-init` skill.
4. **Halt on failure.** If `js-project-init` fails, **stop `/build`** and report the failure — do not proceed to Step 2 or any implementation step.

The user sees no more than one line of output before `js-project-init` runs, and nothing at all when the gate is skipped.

### 2. Verify plan status

Read the plan file. If the status is not `approved`, ask the user: "This plan has status '<status>'. Approve it before building, or continue anyway?"

### 3. Verify acceptance criteria (gate)

Before implementation begins, dispatch a spec-compliance-review subagent in **criteria verification mode** (see `${CLAUDE_PLUGIN_ROOT}/prompts/spec-reviewer.md` § Pre-build criteria verification mode). Pass the plan's acceptance criteria and per-step test expectations.

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

Work the plan **wave by wave** (the plan's `## Parallelization` section, derived by `scripts/plan-waves.sh`). Within a wave, independent slices may build concurrently; across waves a barrier holds the next wave until the current one reconciles green.

**Resolve the wave schedule and concurrency first:**

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/build-wave.sh <plan-file>          # ordered waves + members
bash ${CLAUDE_PLUGIN_ROOT}/scripts/build-jobs.sh --wave-width <W> [--jobs N]  # effective concurrency
```

`build-jobs.sh` resolves `min(--jobs, DEV_TEAM_MAX_PARALLEL_BUILDS, wave width)` (default max **2**; non-positive/non-integer clamp to 1). **Sequential fallback:** when effective concurrency is **1** (a fully-dependent plan, `--jobs 1`, or max 1), build slices one at a time in a single worktree in dependency order — **no worktree fan-out, no reconcile step** (today's behavior exactly).

**Concurrent dispatch (effective concurrency > 1):**

1. Dispatch each independent slice in the wave to its **own** git worktree (`isolation: "worktree"`), up to the effective concurrency. Each slice's changes stay isolated until reconcile, and each slice still runs its full RED-GREEN-REFACTOR and inline review gates.
2. **Report the concrete level and cost**, e.g. *"building wave 2 — 2 slices concurrently; faster wall-clock but burns token budget faster."*
3. **Barrier + reconcile** once the wave's slices finish: `build-wave-reconcile.sh --into <integration> --base <ref> --test-cmd "<full suite>" <slice-branch>...` merges them order-independently and gates on the full suite before any next-wave slice starts.
4. **Loud halt, never silent:**
   - A **failing slice** → exit non-zero naming it, list which same-wave slices succeeded and where their (preserved) worktrees are, print the resume command, and start no next-wave slice. Resume rebuilds only the incomplete slice.
   - A **reconcile conflict** (two same-wave diffs touch one file) → exit non-zero naming the file, pick no side, start no next-wave slice.

For each step within a slice, dispatch implementation following the implementer template (`${CLAUDE_PLUGIN_ROOT}/prompts/implementer.md`). Pass the implementer its step **and the slice's Gherkin scenario(s)** — the scenarios are the behavioral contract the step's test must satisfy.

1. **RED** — Write the failing test described in the step, covering the slice scenario it traces to. Run the test suite. **Hard gate: the new test must fail.** Paste the failing output. If the test passes without new code, the behavior already exists — pick a different test. Do NOT proceed to GREEN without pasted failing output.
2. **GREEN** — Write the minimum implementation to make the failing test pass. Do not add behavior beyond what the test requires. Run the test suite. **Hard gate: all tests must pass.** Paste the passing output. Do NOT proceed without pasted passing output.
3. **REFACTOR** — Clean up structure, naming, duplication without changing behavior. Run tests again — they must still pass. If tests break, undo and try a smaller change.
4. **Inline review checkpoint** — Route review depth based on the step's **Complexity** classification:
   - **trivial**: Skip inline review. The final `/code-review` (step 6) covers all modified files.
   - **standard**: Run `/review-agent spec-compliance-review` against changed files. If it passes, run quality review agents relevant to what changed. If review finds actionable issues (error/warning with high/medium confidence), auto-fix and re-run failed agents (up to 5 iterations per the review-fix loop in `agents/orchestrator.md`). Escalate to user if the loop doesn't converge.
   - **complex**: Run `/review-agent spec-compliance-review`, then the full quality agent suite including opus-tier agents (security-review, domain-review, arch-review). Same review-fix loop applies.
   - If no complexity is specified, default to **standard**.
   - **UI changes (any complexity)**: After quality review passes, run browser verification via `/browse` in automated smoke test mode. Skip with warning if the dev server is not running. See `agents/orchestrator.md` Stage 3.
5. **Mark step done** — Use the Edit tool to update the plan file's `## Build Progress` section on disk:
   - Change `- [ ] Step N.M: <title>` to `- [x] Step N.M: <title>` for the completed step.
   - When every step under a slice is `[x]`, check off the parent `- [ ] Slice N: <title>`.
   - For each acceptance criterion verified by this step, change `- [ ]` to `- [x]` in the Build Progress `### Acceptance Criteria` subsection.
   - After all slices are `[x]`, change `**Status**: approved` to `**Status**: in-progress`.
   - This disk write is the durable commit. If a `/clear` occurs, `/continue` reads `## Build Progress` to determine the resume point without needing conversation history.

### 5. Run full test suite

After all steps are complete, run the full test suite. Paste the output as final verification evidence.

### 6. Run code review

Run `/code-review` against all files modified during the build.

### 7. Update plan status

Use the Edit tool to change `**Status**: in-progress` to `**Status**: implemented` in the plan file. Briefly confirm completion and direct the user to `/pr`.

## Escalation

Stop and ask the user when:

- A test fails for an unexpected reason after 3 attempts
- The plan requires architectural decisions not covered by the plan
- A review checkpoint fails after 2 correction iterations
- You discover the plan is incomplete or contradictory

## Integration

- `/specs` produces the intent, architecture, and acceptance-criteria artifacts that inform the plan
- `/plan` decomposes the feature into slices, authors each slice's Gherkin, and produces the plan this command executes
- `/code-review` runs the full review suite after implementation
- `/pr` creates the pull request after a successful build
- `/continue` can resume a partially completed build across sessions
- The progress-guardian agent tracks step completion against the plan
