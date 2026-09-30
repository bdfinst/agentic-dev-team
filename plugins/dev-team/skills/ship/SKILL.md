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
allowed-tools: Read, Glob, Grep, Bash(gh pr *), Bash(gh issue *), Bash(git branch *), Bash(git rev-parse *), Bash(git fetch *), Bash(python3 *), Skill(specs *), Skill(plan *), Skill(build *), Skill(code-review *), Skill(pr *), AskUserQuestion
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

Resolve the **issue set** from `$ARGUMENTS`: the explicit issue number(s)
(`--issues` list, or one number/URL), else stop and ask — the guard keys off
tracker/PR state, **never** off conversation memory, so a re-fired command
string (a `ScheduleWakeup`/loop prompt) lands on the same verdict. Then run the
deterministic guard (issue numbers are separate argv elements, validated
`^[0-9]+$`; the script rejects anything else):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ship_resume_guard.py" --issues <n1[,n2,...]>
```

It probes PR state (`Closes #N` bodies and `issue-<N>` / `issues-<n1>-<n2>-...`
head branches, cross-repo heads never qualify as `/ship`'s own), issue state,
and spec/plan artifacts, and prints a JSON `verdict` plus the `signal` that
fired. Report the signal so the decision is auditable, then act:

| verdict | action |
|---|---|
| `shipped` | Report the merged PR / closed issues and stop. No phase re-runs. |
| `monitor` | Report the PR and `gh pr checks <pr>`. If `BEHIND` main, rebase onto `main` and hand back to its checks; otherwise wait on the open gate — a re-check timer follows [`knowledge/long-run-waiting.md`](../../knowledge/long-run-waiting.md). Do **not** re-enter spec→plan→build. |
| `resume` | Continue from the earliest incomplete phase against the existing artifacts (`--skip-spec` when the epic exists; build onto the existing branch). Before writing any artifact that would duplicate one, `AskUserQuestion` to confirm resume-vs-restart. |
| `partial-batch` | Some `--issues` members closed, others open, no own batch PR: halt, report which members closed and how, and `AskUserQuestion` whether to re-form the batch from the still-open members or halt. |
| `batch-blocked` | A foreign open PR covers a member: halt the **whole batch** (no partial subset ships), post one comment on **every member issue** naming the in-flight PR — only if an equivalent `/ship` halt comment does not already exist (check first) — and take no further action this round. |
| `first-run` | Proceed to the approach screen. |
| `probe-failed` | Do not assume `first-run`: report the error and `AskUserQuestion`. |

For a batch, the stable key is `issues-<n1>-<n2>-...` (sorted), as defined in
Parse Arguments.

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

First check whether `/build`'s checkpoints already reviewed this exact change:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ship_review_gate.py" --files <the branch's changed files>
```

`{"skip": true}` means every applicable lens has a ledger `pass` at each file's
current content — skip the pass and say so in the Step 7 report (list the
cleared lenses). Anything else (including any doubt: no ledger, edited since,
unhashable file) runs the pass as below. `--force-restart` never skips.

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
