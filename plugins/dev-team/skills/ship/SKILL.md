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
argument-hint: "<feature-description> [--skip-spec] [--no-auto-merge] [--force-restart]"
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
5. **Idempotent per issue.** Never re-run the pipeline for an issue that is
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

## Workflow-state transitions (#1166)

At the start of each phase below (2-6), append one state-transition event so
`/run-report` and friends can derive dwell time per phase — never skip this
even when a phase resumes/monitors rather than running fresh:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/workflow_state.py record \
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
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/iteration_journal_gate.py record \
  --round-id "<issue-identifier>" \
  --attempted "<short note: which phase just ran>" \
  --outcome "<short note: passed|failed|blocked>" \
  --next-action "<short note: next phase or stop>" \
  --session "$CLAUDE_SESSION_ID"

python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/iteration_journal_gate.py check \
  --round-id "<issue-identifier>" \
  --session "$CLAUDE_SESSION_ID"
```

`<issue-identifier>` is the same identifier the Step 1a resume guard resolves
(explicit issue number/URL, or feature slug). If `check` exits non-zero, do
not advance to the next phase — retry `record` before continuing.

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

1. **PR** — `gh pr list --state all --search "<N>"` and
   `gh pr list --state all --head issue-<N>`. A PR whose body carries
   `Closes #<N>` (or whose head branch matches) is the strongest signal.
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
  `main` and hand back to its checks; otherwise wait on the open gate. Do
  **not** re-enter spec→plan→build.
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

#### 1b. Approach screen

Once the guard confirms a genuine first run (or `--force-restart` was given),
screen the request against `${CLAUDE_PLUGIN_ROOT}/knowledge/decision-defaults.md`. Surface any ambiguous
axis to the user in a single batch and get the answers before proceeding. Stop here if
a genuinely blocking ambiguity remains.

### 2. Spec (unless `--skip-spec`)

Invoke `/specs` for the feature. `/specs` runs the Ambiguity Resolution Protocol
before finalizing acceptance criteria — any finding classified `requires-stakeholder-input`
is surfaced to the human as a required answer, not an optional confirmation.

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
