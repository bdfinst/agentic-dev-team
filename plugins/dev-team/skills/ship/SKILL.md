---
name: ship
description: >-
  Run the full spec-to-merge pipeline as one command: spec, plan, small-batch build,
  code review, and a PR with auto-merge — pausing at the existing human gates.
  Idempotent per issue — a re-invocation for work already shipped or in-flight
  resumes/monitors instead of re-running the pipeline.
  Use when the user says "ship this", "take this feature end to end",
  "implement this issue", "we need to build", or wants the
  spec->plan->build->PR flow without re-assembling it each time.
argument-hint: "<feature-description> [--skip-spec] [--no-auto-merge] [--force-restart] [--issues <n1,n2>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash(gh pr *), Bash(gh issue *), Bash(git branch *), Bash(git rev-parse *), Bash(git fetch *), Skill(specs *), Skill(plan *), Skill(build *), Skill(code-review *), Skill(pr *), AskUserQuestion
---

# Ship

Role: orchestrator. This command chains the existing pipeline skills end to end; it
does not implement, review, or merge anything itself — each phase is delegated to the
skill that owns it, and the existing human approval gates are preserved.

You have been invoked with the `/ship` command.

## Orchestrator constraints

1. **Delegate every phase.** Call the owning skill (`/specs`, `/plan`, `/build`,
   `/code-review`, `/pr`); do not re-implement their logic here.
2. **Honor the human gates.** Do not advance past a gate without explicit approval —
   this command sequences phases, it does not remove their review points.
3. **Confirm the approach first.** Before planning, screen the request against
   `${CLAUDE_PLUGIN_ROOT}/knowledge/decision-defaults.md` and confirm any ambiguous high-reversal-cost axis
   (replace-vs-merge, format fidelity, migrate-vs-edit-stub, scope) in one batch.
4. **Be concise.** Report each phase's outcome and the next gate, nothing more.
5. **Agent-dispatch capability is a pipeline-wide precondition, enforced by the delegated skills, not duplicated here (issue #1461).** `/plan` (Step 5b), `/build` (Steps 3, 4, 6), and `/code-review` (Step 4) each independently confirm the `Agent`/`Task` tool is present before dispatching any review agent, and each hard-fails — STOP, no self-applied review, no gate file written — when it is missing. `/ship` does not re-check or restate that logic; if a delegated phase halts on missing dispatch capability, `/ship` reports that halt and stops with it (per constraint 2, "Honor the human gates") rather than working around it or advancing past the phase that failed.
6. **Idempotent per issue.** Never re-run the pipeline for an issue that is
   already shipped or in-flight. The Step 1 resume guard decides this from
   durable tracker/PR state — not conversation memory — so a re-fired command
   string (e.g. a `ScheduleWakeup`/loop prompt that repeats) lands on
   resume/monitor, not a second spec→plan→build→PR pass.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: the feature description (required).
- `--skip-spec`: Skip the spec phase (use when a spec already exists for this work).
- `--no-auto-merge`: Pass through to `/pr` so the PR is not set to auto-merge.
- `--force-restart`: Bypass the Step 1 resume guard and re-run the pipeline from
  the start even when prior artifacts exist. Use only for a deliberate rebuild —
  it accepts the risk of duplicate spec issues, sub-issues, and PRs.
- `--issues <comma-separated-list>`: dispatch this run as a **batch** covering
  every listed issue number, producing one shared spec, one shared plan, and
  one PR that closes every member issue. Mutually exclusive with treating
  `$ARGUMENTS`'s positional feature description as a single-issue identifier —
  when `--issues` is given, the feature description still describes the
  batch's overall work, but the resume guard and every downstream phase
  operate over the full issue-number set, not one issue. Each token must be
  a bare issue number (`^[0-9]+$` after trimming); reject the whole
  invocation with a clear error naming the offending token otherwise — never
  coerce or best-effort parse. Issue numbers are passed to `gh` as separate
  argv elements, never interpolated into a shell string. When `--issues` was
  given, `<issue-identifier>` for every iteration-journal-gate call in this
  run is the batch's stable key: the sorted member issue numbers joined as
  `issues-<n1>-<n2>-...` (e.g. `issues-101-102-103`) — used identically
  across every phase of this run, never re-derived differently per phase.

## Workflow-state transitions (#1166)

At the start of each phase below (2-6), append one state-transition event so
`/run-report` and friends can derive dwell time per phase — never skip this
even when a phase resumes/monitors rather than running fresh:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/workflow_state.py" record \
  --workflow ship --prior-state <PRIOR> --new-state <NEW> --session "$CLAUDE_SESSION_ID"
```

Map phases to canonical states: Spec→`SPEC`, Plan→`PLAN`, Build→`BUILD`,
Review→`REVIEW`, PR→`PR` (an extra `COMMIT` transition is optional — most
commits happen inside `/build`). Omit `--prior-state` only for the very first
transition of a run. This is a model-authored, fail-open append (same
convention as `.claude/metrics/review-value.jsonl`) — never let it block a phase.

## Iteration journal gate (#1168)

Before advancing from one phase (2-6) to the next, append a structured
decision entry and confirm the gate allows advancement — a hard block,
distinct from the advisory, plan-step-keyed `progress-guardian` gate:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/iteration_journal_gate.py" record \
  --round-id "<issue-identifier>" \
  --attempted "<short note: which phase just ran>" \
  --outcome "<short note: passed|failed|blocked>" \
  --next-action "<short note: next phase or stop>" \
  --session "$CLAUDE_SESSION_ID"

python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/iteration_journal_gate.py" check \
  --round-id "<issue-identifier>" \
  --session "$CLAUDE_SESSION_ID"
```

`<issue-identifier>` is the same identifier the Step 1a resume guard resolves
(explicit issue number/URL, or feature slug) — or, when `--issues` was given,
the batch key defined in Parse Arguments (`issues-<n1>-<n2>-...`). If `check`
exits non-zero, do not advance to the next phase — retry `record` before
continuing.

## Steps

### 1. Approach contract

#### 1a. Resume guard — run before anything else

`/ship` is idempotent per issue. Before screening the approach or invoking
`/specs`, check whether this work has **already been shipped or is in-flight**,
so a re-invocation resumes or monitors instead of duplicating the spec issue,
the sub-issues, and the PR. Skip this guard only when `--force-restart` was
given (a deliberate rebuild).

First, resolve the **issue identifier** from `$ARGUMENTS`: an explicit issue
number or URL if present, otherwise the feature slug. Derive the conventional
branch name for it (this repo names feature branches `issue-<N>`). Then probe
three durable signals — key off tracker/PR state, **never** off whether this
conversation has run the pipeline, so a re-fired command string (a
`ScheduleWakeup`/loop prompt) hits the same guard:

**When `--issues <comma-separated-list>` was given**, resolve the full set of
issue numbers instead of one identifier: every probe below runs once **per
issue in the set**, and the verdict is decided over the whole set (see "Batch
verdict" below) rather than per member in isolation. When `--issues` is
absent, the set is just the single resolved identifier and the guard behaves
exactly as documented next — solo behavior is unmodified by this flag's
existence.

1. **PR** — `gh pr list --state all --search "<N>"` and
   `gh pr list --state all --head issue-<N>`. A PR whose body carries
   `Closes #<N>` (or whose head branch matches) is the strongest signal.
   **When `--issues` was given**, also probe the batch's own branch:
   `gh pr list --state all --head issues-<n1>-<n2>-...` — this is the sole
   input the Batch verdict's head-branch-match check (below) reads.
2. **Spec / sub-issues** — an existing spec epic and its linked slice
   sub-issues for the feature. Because `/specs` searches by `Spec: <Feature
   Name>` title, an epic titled conventionally (`feat: …`) will not be found by
   `/specs` itself — so match on the issue number here, not the title.
3. **Plan** — an approved/implemented plan (a linked plan sub-issue on
   GitHub-connected repos, or a plan file under `docs/specs/**/plans/` or
   `plans/`).

Decide from what the probes return — and treat every treatment as reporting,
not re-running:

- **Merged PR closing the issue → already shipped.** Report the merged PR and
  stop. Do not re-run any phase.
- **Open PR for the issue → in-flight; MONITOR.** Report the PR and its CI
  state (`gh pr checks <pr>`). If the PR is `BEHIND` main, rebase it onto
  `main` and hand back to its checks; otherwise wait on the open gate — if you
  arm a timer to re-check, follow
  [`knowledge/long-run-waiting.md`](../../knowledge/long-run-waiting.md), whose
  contract makes the re-fired prompt this guard already expects. Do **not**
  re-enter spec→plan→build.
- **Spec / sub-issues / plan exist but no PR yet → partially in-flight;
  RESUME.** Continue from the earliest incomplete phase against the existing
  artifacts (e.g. `--skip-spec` when the spec epic already exists; build onto
  the existing branch) rather than creating new ones. Before writing any
  artifact that would duplicate an existing one, use `AskUserQuestion` to
  confirm resume-vs-restart.
- **Nothing found → genuine first run.** Proceed to the approach screen below.

When the guard resumes/monitors or stops, report which signal fired (PR number,
epic/sub-issue numbers, plan location) so the decision is auditable, and skip
the remaining first-run steps that the existing artifacts already satisfy.

##### Batch verdict (`--issues` only)

When `--issues` was given, decide the verdict over the **whole set**, never
per member in isolation. The branches below are evaluated in the order
listed, and the first whose condition holds wins — this is what lets
"fully shipped" win over an unrelated open PR on an already-merged batch, as
long as it is checked first:

- **Every member issue closed (by a merged PR or otherwise) — whether by
  the same PR/path or different ones — → fully shipped.** Same treatment as
  the single-issue "already shipped" case above: report each member's
  closure — the merged PR when there is one, or otherwise how it closed
  (e.g. closed as not-planned, closed manually) — and stop. Do not re-run
  any phase.
- **Some but not all members already closed (by a merged PR or otherwise),
  others not → malformed/partially-shipped batch — unless the still-open
  members are covered by the batch's own open PR (per the head-branch check
  below), in which case this is normal incremental progress: fall through
  to the batch-blocked branch's MONITOR treatment instead of halting.**
  Otherwise, halt and report which members are already closed and how each
  closed (merged PR, or otherwise) — do not resume the pipeline over a
  batch with mixed shipped state. Use `AskUserQuestion` to confirm whether
  to re-form the batch from only the still-open members, or halt entirely.
- **Any member has an open PR whose body carries `Closes #<N>` or whose head
  branch matches that member's conventional branch — not merely one whose
  title/body mentions the number in passing → batch-blocked.** This is a
  distinct case from the single-issue "in-flight; MONITOR" verdict above,
  and it must be named explicitly — never silently folded into that
  single-issue treatment. The batch's own conventional branch is the same
  batch key defined in Parse Arguments used as a branch name:
  `issues-<n1>-<n2>-...`. When the open PR's head branch matches that batch
  branch **and the PR is not cross-repository** (`gh pr view <pr> --json
  isCrossRepository,headRepositoryOwner`; a fork can name its branch
  anything, including this one, so a same-named cross-repo branch never
  qualifies) — meaning it's genuinely /ship's own PR from an earlier round,
  not a third party's — apply the same MONITOR treatment as the single-issue
  case above (`gh pr checks <pr>`; rebase onto `main` if `BEHIND`). Otherwise
  (a different PR, a cross-repository PR merely sharing the branch name, or
  one whose body happens to carry `Closes #<N>` for a member — a PR body and
  a fork's branch name are both third-party-controllable, so neither alone
  exempts a halt): halt dispatch of the **whole batch** this round (no
  partial subset ships), post a comment on **every member issue** naming which
  one is already in-flight — only if an equivalent /ship halt comment does
  not already exist on that issue (check existing comments first); a
  re-fired invocation must not re-post — and take no further ship action on
  any member this round.
- **Otherwise → proceed as today's "genuine first run" / "partially in-flight;
  RESUME" logic**, evaluated across the whole issue set rather than a single
  issue — e.g. `--skip-spec` when the shared spec epic already exists; build
  onto the existing shared branch.

#### 1b. Approach screen

Once the guard confirms a genuine first run (or `--force-restart` was given),
screen the request against `${CLAUDE_PLUGIN_ROOT}/knowledge/decision-defaults.md`. Surface any ambiguous
axis to the user in a single batch and get the answers before proceeding. Stop here if
a genuinely blocking ambiguity remains.

### 2. Spec (unless `--skip-spec`)

Invoke `/specs` for the feature. `/specs` runs the Ambiguity Resolution Protocol
before finalizing acceptance criteria — any finding classified `requires-stakeholder-input`
is surfaced to the human as a required answer, not an optional confirmation.
When `--issues` was given, `/specs` is invoked **once** for the whole batch's
combined feature description — one shared spec covering every member issue.
If `/specs`' own Scope Split Protocol determines the members describe
genuinely unrelated features, that split is `/specs`' existing human gate —
surface it and stop, rather than overriding it to force one spec.

**These unresolved items ARE the human gate.** Do not auto-approve past them, even in
non-interactive mode. The only exception is `--skip-spec` (when a reviewed spec already
exists). A spec that passed its consistency gate with undocumented assumptions is not
an approved spec.

Present the completed spec (Intent, Architecture, Acceptance Criteria, and Ambiguity
Log) for human review. **Human gate** — wait for approval before planning.

### 3. Plan

Invoke `/plan` with the (approved) spec. The plan decomposes the feature into vertical
slices with Gherkin scenarios and states the chosen stance on any decision-defaults
axis. **Human gate** — wait for plan approval before building.
When `--issues` was given, `/plan` is likewise invoked **once** for the whole
batch — one shared plan covering every member issue, never one plan per issue.

### 4. Build

Invoke `/build` to execute the approved plan in small per-behavior batches (code-first),
with inline review checkpoints and verification evidence. Do not proceed until the build reports a green
suite.

### 5. Review

Invoke `/code-review` over the changes and let its fix loop converge. Surface any
findings that need human judgment.

This dispatch deliberately omits `--internal`: `/ship` is a top-level,
human-typed command, and this Review phase is its pipeline's human-facing
quality gate, so `/code-review` writing its usual `.dev-team-reports/code-review.md`
report here is intentional — see `knowledge/report-output-location.md`'s
"Report exception: /ship" section, not an unfixed oversight.

### 6. PR

Invoke `/pr` (passing `--no-auto-merge` only if it was given to `/ship`). `/pr` runs
the pre-PR quality gate, opens the PR, and — by default — enables auto-merge so it
lands once checks pass. **Human gate** — the PR is the final review artifact.

When `--issues` was given, the resulting PR body must carry one `Closes #<N>`
line per member issue — not just one — so merging it closes every batch
member. `/pr`'s existing closing-keyword-lint guidance
(`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_close_keyword_lint.py"`, see
`skills/pr/SKILL.md`) needs no change to support this: it already lints each
`Closes #<N>` line independently, so a batch PR body simply carries more of
them. `/ship` confirms the created PR body actually carries one such line
per member before reporting success; if any is missing, state the gap
explicitly rather than silently reporting the batch as shipped.

### 7. Report

Report the PR URL, the quality-gate result, and whether auto-merge is armed.

## Notes

- `/ship` is sequencing only: every gate, fix loop, and evidence requirement comes from
  the underlying skills. If any phase stops at a gate, `/ship` stops with it.
- For a plan-only pass, use `/plan`; for build-only, use `/build`. `/ship` is for the
  whole loop in one invocation.
- Re-invoking `/ship` for an issue that is already shipped or in-flight is safe:
  the Step 1 resume guard (1a) reports/monitors instead of re-running. Pass
  `--force-restart` only when a deliberate rebuild is intended.
