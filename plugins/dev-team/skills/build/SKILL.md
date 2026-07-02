---
name: build
description: >-
  Execute an approved implementation plan using TDD. Reads the plan, implements
  each step with RED-GREEN-REFACTOR, runs inline review checkpoints, and
  produces verification evidence. Use when the user says "build this", "implement
  the plan", "start building", or after /plan has been approved.
argument-hint: "[--plan <path>] [--yes]"
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
5. **Review checkpoints (granularity scales with complexity).** Run inline review (spec-compliance first, then quality agents) per step for `complex` steps; batch `standard`/`trivial` steps into one review at the slice boundary. Record each checkpoint's find/fix/no-op outcome to `metrics/review-value.jsonl`. The final `/code-review` is the backstop.
6. **Be concise.** Report step status and verification evidence, no narration.
7. **Diagnose before retry.** When any bash command run during the build fails (a script, a test run, a build-tooling invocation), read the exit code and error text and state a one-line cause hypothesis before correcting and re-issuing it. Never re-run a failed command unmodified. If the shallow diagnosis reveals a real defect rather than a shell-level mistake (bad path, typo, missing arg), escalate to Systematic Debugging per the Escalation section below.

## Parse Arguments

Arguments: $ARGUMENTS

- `--plan <path>`: Path to the plan file. If omitted, search `plans/` for the most recently modified plan with status `approved`.
- `--yes`: Auto-approve the build's approval gates (steps 2 and 3) without prompting (non-interactive opt-in).

**Interactivity.** The run is **non-interactive** when any of these hold: `--yes` was passed, `DEV_TEAM_AUTO_APPROVE=1` is set, or stdin is not a usable TTY (`test -t 0` is false — the headless/CI/automation case). The approval gates in steps 2 and 3 use this: interactive runs prompt exactly as before; non-interactive runs auto-proceed and **record the bypass in the build output** rather than hanging.

## Steps

### 0. Context loading

Invoke the [Context Loading Protocol](../context-loading-protocol/SKILL.md) at the start of this task. It decides which agents and skills to load for the current phase, and sets the context budget before any implementation work begins. This is a lightweight read — it does not add agents to context; it decides the load order so context stays under the 40% ceiling throughout the build.

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

Read the plan file. If the status is not `approved`:

- **Interactive** → ask the user: "This plan has status '<status>'. Approve it before building, or continue anyway?"
- **Non-interactive** (see Parse Arguments) → do **not** block. Auto-approve and continue, and print an explicit audit line into the build output: `Auto-approved plan status '<status>' (non-interactive) — no human gate. Trigger: <--yes | DEV_TEAM_AUTO_APPROVE=1 | no TTY>.`

### 3. Verify acceptance criteria (gate)

Before implementation begins, dispatch a spec-compliance-review subagent in **criteria verification mode** (see `${CLAUDE_PLUGIN_ROOT}/prompts/spec-reviewer.md` § Pre-build criteria verification mode). Pass the plan's acceptance criteria and per-step test expectations.

The reviewer evaluates each criterion for:

- **Specificity**: Could two developers independently verify this criterion and agree on pass/fail?
- **Testability**: Can this criterion be validated with a test or observable output?
- **Completeness**: Are edge cases and error conditions addressed?

If any criteria are flagged:

1. Present the findings to the user with the reviewer's suggested improvements
2. **Interactive** → Ask: "Revise these criteria before building, or proceed anyway?"
   - If the user overrides, log the override in the build output and continue
   - If the user revises, update the plan file and re-verify
3. **Non-interactive** (see Parse Arguments) → do **not** block. Proceed and record the bypass in the build output: `Acceptance-criteria gate auto-passed with N flagged criterion(s) (non-interactive) — no human gate. Trigger: <--yes | DEV_TEAM_AUTO_APPROVE=1 | no TTY>.` Include the flagged findings in the record so the bypass is auditable.

### 4. Implement each step

Work the plan **wave by wave** (the plan's `## Parallelization` section, derived by `scripts/plan_waves.py`). Within a wave, independent slices may build concurrently; across waves a barrier holds the next wave until the current one reconciles green.

**Base-ref check (top-level session, before any subagent dispatch).** Worktree subagents (`isolation: "worktree"`) must branch from the caller's local HEAD, not `origin/<default>`, so the `docs/specs/<slug>.md` and `plans/<slug>.md` files `/ship` just produced are visible to them (issue #553). This is controlled by Claude Code's `worktree.baseRef` setting, which is honored only at project (`.claude/settings.json`) or user (`~/.claude/settings.json`) scope — **not** at plugin or project-local scope (`docs/spikes/worktree-baseref-head-spike.md`). `/build` cannot set this on the user's behalf, so it runs a read-only detect-and-warn **in this top-level `/build` session, before any subagent dispatch**, so the warning is visible in the human-facing transcript:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/build_worktree_baseref.py detect   # prints head|fresh|unset|unknown
```

- **`head`** → no warning. Proceed.
- **`fresh`**, **`unset`**, or **`unknown`** (detection failed — e.g. `jq` unavailable; treated fail-safe) → unless `DEV_TEAM_WORKTREE_BASE_FRESH=1` is set, print a loud warning naming the exact file to edit and a paste-ready snippet, then continue:

  ```
  ⚠ worktree.baseRef is not "head" (detected: <value>) — worktree subagents
  will branch from origin/<default>, not your current HEAD. Any
  uncommitted-to-origin spec/plan/WIP files will be invisible to them.

  Add this to .claude/settings.json (project) or ~/.claude/settings.json
  (user) — plugin and project-local settings.json are NOT honored for
  this key:

    { "worktree": { "baseRef": "head" } }

  To keep fresh-from-origin worktrees deliberately, set
  DEV_TEAM_WORKTREE_BASE_FRESH=1 to silence this warning.
  ```

  If detection returned `unknown`, the warning additionally states that `worktree.baseRef could not be detected`.

**`/build` never mutates a settings file.** The check is read-only end to end — it never writes `.claude/settings.json`, `~/.claude/settings.json`, or any other settings file. There is nothing to restore and no crash-recovery surface.

**Resolve the wave schedule and concurrency first:**

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_wave.py <plan-file>          # ordered waves + members
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_jobs.py --wave-width <W> [--jobs N]  # effective concurrency
```

`build_jobs.py` resolves `min(--jobs, DEV_TEAM_MAX_PARALLEL_BUILDS, wave width)` (default max **2**; non-positive/non-integer clamp to 1). **Sequential fallback:** when effective concurrency is **1** (a fully-dependent plan, `--jobs 1`, or max 1), build slices one at a time in a single worktree in dependency order — **no worktree fan-out, no reconcile step** (today's behavior exactly).

**Concurrent dispatch (effective concurrency > 1):**

1. Dispatch each independent slice in the wave to its **own** git worktree (`isolation: "worktree"`), up to the effective concurrency. Each slice's changes stay isolated until reconcile, and each slice still runs its full RED-GREEN-REFACTOR and inline review gates.
2. **Report the concrete level and cost**, e.g. *"building wave 2 — 2 slices concurrently; faster wall-clock but burns token budget faster."*
3. **Barrier + reconcile** once the wave's slices finish: `build_wave_reconcile.py --into <integration> --base <ref> --test-cmd "<full suite>" <slice-branch>...` merges them order-independently and gates on the full suite before any next-wave slice starts.
4. **Loud halt, never silent:**
   - A **failing slice** → exit non-zero naming it, list which same-wave slices succeeded and where their (preserved) worktrees are, print the resume command, and start no next-wave slice. Resume rebuilds only the incomplete slice.
   - A **reconcile conflict** (two same-wave diffs touch one file) → exit non-zero naming the file, pick no side, start no next-wave slice.

For each step within a slice, dispatch implementation following the implementer template (`${CLAUDE_PLUGIN_ROOT}/prompts/implementer.md`). Pass the implementer its step **and the slice's Gherkin scenario(s)** — the scenarios are the behavioral contract the step's test must satisfy.

Within the RED/GREEN/REFACTOR mini-cycle below, repeated Write/Edit calls can race a `PostToolUse` hook that rewrites files (e.g., a formatter): an `Edit` failing on a stale `old_string` is expected to self-correct by re-`Read`ing the file before the next `Edit` attempt, not to escalate immediately.

1. **RED** — Write the failing test described in the step, covering the slice scenario it traces to. Run the test suite. **Hard gate: the new test must fail.** Paste the failing output. If the test passes without new code, the behavior already exists — pick a different test. Do NOT proceed to GREEN without pasted failing output.
2. **GREEN** — Write the minimum implementation to make the failing test pass. Do not add behavior beyond what the test requires. Run the test suite. **Hard gate: all tests must pass.** Paste the passing output. Do NOT proceed without pasted passing output.
3. **REFACTOR** — Clean up structure, naming, duplication without changing behavior. Run tests again — they must still pass. If tests break, undo and try a smaller change.
4. **Inline review checkpoint — granularity scales with complexity.** *Where* the checkpoint runs depends on the step's **Complexity** classification (review *depth* still scales too):
   - **trivial**: Skip inline review. The final `/code-review` (step 6) covers all modified files.
   - **standard**: **Defer** review to the slice boundary (sub-step 6) — do not review now. Track the step's changed files so the slice checkpoint reviews them in one batch. Per-step review on standard steps is N near-identical passes where one at slice end largely does the same work, and the final `/code-review` (step 6) remains the backstop. This is the batching win — fewer review dispatches per multi-step slice at bounded quality risk.
   - **complex**: Review **now, per step** — smaller blast radius per fix. Run `/review-agent spec-compliance-review`, then the full quality agent suite including opus-tier agents (security-review, domain-review, arch-review), with the review-fix loop (up to 5 iterations per `agents/orchestrator.md`). Escalate to user if the loop doesn't converge. Then **record the checkpoint outcome** (sub-step 7).
   - If no complexity is specified, default to **standard**.
   - **UI changes (any complexity)**: After the relevant review passes (per-step for complex, at the slice checkpoint for standard), run browser verification via `/browse` in automated smoke test mode. Skip with warning if the dev server is not running. See `agents/orchestrator.md` Stage 3.
5. **Mark step done** — Use the Edit tool to update the plan file's `## Build Progress` section on disk:
   - Change `- [ ] Step N.M: <title>` to `- [x] Step N.M: <title>` for the completed step.
   - When every step under a slice is `[x]`, check off the parent `- [ ] Slice N: <title>`.
   - After all slices are `[x]`, change `**Status**: approved` to `**Status**: in-progress`.
   - This disk write is the durable commit. If a `/clear` occurs, `/continue` reads `## Build Progress` to determine the resume point without needing conversation history.
6. **Slice review checkpoint (batched).** When every step under the current slice is `[x]` **and** the slice had any deferred `standard` (or unspecified) steps, run **one** review pass over the slice's accumulated changed files: `/review-agent spec-compliance-review`, then the quality review agents relevant to what changed. Apply the same review-fix loop (up to 5 iterations; escalate if it doesn't converge). `trivial`-only and all-`complex` slices have nothing to batch — skip this pass. Then **record the checkpoint outcome** (sub-step 7).
7. **Record review value (#348).** For **each** checkpoint that runs (per-step `complex` in sub-step 4, and per-slice in sub-step 6), append one JSON line to `metrics/review-value.jsonl` capturing whether review actually changed anything — counts and outcomes only, never code or file content (consistent with the cost meter's privacy boundary). Schema in `performance-metrics`:

   ```json
   {"timestamp":"<ISO8601>","plan":"<plan-file>","slice":"<N>","step":"<N.M or all>","checkpoint":"step|slice","complexity":"standard|complex","agents_run":["spec-compliance-review","..."],"issues_found":0,"issues_fixed":0,"fix_iterations":0,"outcome":"no-op|fixed|escalated"}
   ```

   `outcome` is `no-op` when the checkpoint passed clean (found nothing), `fixed` when it found and auto-fixed actionable issues, `escalated` when the loop didn't converge. This is the sensor that tells a build where review caught a real defect from one where every loop passed no-op — it turns the pipeline's "value untested" into "value measured" and feeds the plan/step tiering decisions. Disable with `DEV_TEAM_REVIEW_VALUE=off`.

### 5. Run full test suite

After all steps are complete, run the full test suite. Paste the output as final verification evidence.

**Quality ownership — the whole suite must be green, not just this branch's tests.** A failing test is a failing test regardless of whether this change caused it: a red suite blocks `/pr` even when the failure pre-dates the branch. Do not wave a failure past as "pre-existing / unrelated." Either fix it (enter [Systematic Debugging](../systematic-debugging/SKILL.md) for the root cause), or — if it is genuinely out of scope — explicitly surface and triage it (`/triage` a record or quarantine it with a reason) and report the suite as **not green**. Never proceed to `/pr` on red by attributing the failure to someone else's change.

### 6. Run code review

Run `/code-review` against all files modified during the build.

### 7. Final test quality score (branch)

Produce a Farley Score for the tests written on this branch — the last quality signal before `/pr`.

1. Resolve the branch base: `git merge-base HEAD origin/HEAD` (fall back to `origin/main`, then `main`, `master`, `develop`).
2. List the branch's changed test files: `git diff --name-only <base>...HEAD`, keeping only test files (indicators in `knowledge/test-file-indicators.md` — `*.test.*` / `*.spec.*` / `__tests__/`, xUnit/JUnit attributes, `.feature` files).
3. If no test files changed on the branch, print one line — `No tests written on this branch — skipping Farley Score.` — and continue to Step 8.
4. Otherwise invoke the `farley-score` skill scoped to those files. Present the suite-level Farley Score, rating, and distribution as the final pre-PR signal. This is **informational** — a low score does not block `/pr`, but surface it so the user can decide whether to revise before opening the PR.

### 8. Update plan status

Use the Edit tool to change `**Status**: in-progress` to `**Status**: implemented` in the plan file. Briefly confirm completion, report the branch Farley Score, and direct the user to `/pr`.

### 9. Learning loop

Invoke the [Feedback & Learning](../feedback-learning/SKILL.md) skill at task completion to capture any correction turns from this session. If the user used correction language during the build (e.g. "no, actually", "revert", "that's wrong", "stop doing X"), record the pattern so it can become an instruction rule. If no corrections occurred, this step is a no-op — invoke and it will report nothing to capture.

## Escalation

A failure is a debugging task first, not a hand-back. Before escalating any test, review, or bash/command failure, run a [Systematic Debugging](../systematic-debugging/SKILL.md) pass — reproduce, find the root cause, state it in one sentence — and escalate **with that diagnosis**, never just an attempt count.

Stop and ask the user when:

- A test still fails *after systematic debugging has identified the root cause* and the fix needs a decision you can't make (e.g. it requires changing the spec or the architecture)
- The plan requires architectural decisions not covered by the plan
- A review checkpoint fails after 2 correction iterations *and* the root cause is understood but unresolvable within scope
- You discover the plan is incomplete or contradictory

## Integration

- `/specs` produces the intent, architecture, and acceptance-criteria artifacts that inform the plan
- `/plan` decomposes the feature into slices, authors each slice's Gherkin, and produces the plan this command executes
- `/code-review` runs the full review suite after implementation
- `farley-score` scores the branch's tests (Farley Score) as the final pre-PR quality signal
- `/pr` creates the pull request after a successful build
- `/continue` can resume a partially completed build across sessions
- `python3 scripts/progress_guardian.py --plan <plan-file>` validates step completion and commit discipline at each step boundary
