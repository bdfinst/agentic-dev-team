---
name: plan
description: >-
  Create a structured implementation plan with goal, acceptance criteria,
  incremental TDD steps, and a pre-PR quality gate. Use this for tasks that
  need a plan but not the full three-phase orchestration, or when the user
  says "plan this", "make a plan", "break this down", or "how should I
  implement this".
argument-hint: "<task-description> [--output <path>] [--yes] [--spec-issue <url>]"
user-invocable: true
allowed-tools: Read, Write, Glob, Grep, Bash(mkdir *), Bash(date *), Bash(git branch *), Bash(test *), Bash(gh issue view *), AskUserQuestion
---

# Plan

Role: orchestrator. This command creates a structured plan — it does not implement anything.

You have been invoked with the `/plan` command.

## Orchestrator constraints

1. **Do not implement.** Produce only the plan. No code, no scaffolding, no file edits beyond the plan file itself. One narrow carve-out: **after approval**, derived `.feature` files are written via the export script `plan_gherkin_export.py` (step 6) — never before approval, never by hand.
2. **Every step is one behavior with a full cycle.** The cadence is Code-First Small Batches — each step follows IMPLEMENT → TEST → REFACTOR (`docs/experiments/RECOMMENDATIONS.md` Rec 3). The refactor runs in every cycle.
3. **Incremental.** Each step must leave the codebase in a working, committable state.
4. **Human approval required.** Present the plan for approval before any implementation begins.
5. **Be concise.** The plan is the artifact; keep chat to decisions and gaps.
6. **State your approach stance.** For any high-reversal-cost axis in `${CLAUDE_PLUGIN_ROOT}/knowledge/decision-defaults.md` the task touches (replace-vs-merge, format fidelity, migrate-vs-edit-stub, auto-merge-vs-direct, scope), state the chosen stance explicitly in the plan so it is visible — and correctable — at the human gate.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: task description (required)
- `--output <path>`: Write plan to a specific path. Default: `plans/<slugified-task>.md`
- `--yes`: Auto-approve the plan without prompting (non-interactive opt-in; see step 6).
- `--spec-issue <url>`: Treat the given GitHub issue as the spec source, bypassing file discovery in step 1 — supplied by `/specs`' GitHub-issue persistence branch, or usable directly by an operator pointing `/plan` at an existing spec issue.

## Steps

### 1. Check for spec artifacts

**If `--spec-issue <url>` was supplied**, skip file discovery entirely: run `gh issue view <url> --json title,body` and extract Intent Description, Architecture Specification, Acceptance Criteria, and Ambiguity Log directly from the issue body — the same headings `/specs`' GitHub-issue persistence branch writes (Ambiguity Log is one more than the file path's three-artifact minimum, so ambiguities `/specs` already resolved with the human stay visible here). This narrowly scoped, read-only call is warranted directly in this step — unlike step 6's "offer GitHub issues" section, which delegates issue *creation* to `/issues-from-plan` — because this step runs before any plan content exists, so there is nothing yet to delegate to. If `gh issue view <url>` exits non-zero (deleted issue, bad URL, expired auth, network down), report the failure and cause to chat — do not silently proceed as if unsupplied — and fall back to the file search below. **Otherwise**, search for specification artifacts produced by `/specs` — look for files matching `docs/specs/**` or `specs/**` related to the task. Check for the three artifacts: Intent Description, Architecture Specification, and Acceptance Criteria. The spec does **not** contain Gherkin — authoring the behavioral scenarios is this command's job. If no spec artifacts are found (by either path), ask the user: "No specification artifacts found for this task. Run `/specs` first to produce them, or continue planning without specs?"

**Non-interactive** (per step 6's interactivity rule): do not prompt — log
`No spec artifacts found — continuing without specs (non-interactive).`, proceed, and
record the absence in the plan's `## Risks & Open Questions` so it reaches the PR's
Decisions & Assumptions section.

If the user chooses to continue without specs, proceed. Otherwise, stop and let them run `/specs` first.

### 2. Understand the task and cut the slices

Read relevant code and context to understand what needs to change. Keep exploration focused — this is planning, not research. If the task is complex enough to need deep research, suggest `/design-doc` instead. If spec artifacts exist, use them as the primary source for goals, constraints, and acceptance criteria. Prefer CodeGraph (`codegraph_explore`/`codegraph_impact`) or Repowise (`get_context`/`search_codebase`) over raw `Grep`/`Read` for this — cheaper blast-radius scoping when either is present; fall back to `Read`/`Grep`/`Glob` when not.

Then **decompose the feature into vertical slices**. A slice is a vertically deliverable increment — independently testable and, ideally, independently shippable. Sequence slices so trunk stays releasable at every step: land incomplete behavior behind a feature toggle or an abstraction, and order any data change as expand-before-contract rather than a single breaking migration (see `knowledge/release-strategies.md` and `knowledge/database-change-management.md`). For each slice, **author the Gherkin scenario(s)** that define its observable behavior. This is where the behavioral contract is written; the spec only described the change and its goals.

When authoring each slice's Gherkin, cover:

- **Happy path** — the primary success behavior.
- **Negative cases** — invalid, unauthorized, missing, or malformed input.
- **Edge cases** — empty collections, boundary values, concurrent access, idempotency.
- **Error scenarios** — specify observable error behavior, not just "should fail".

Keep scenarios implementation-independent (no databases, selectors, or internal data structures in step text) and deterministic. Every acceptance criterion from the spec must be covered by at least one scenario across the slices. Each TDD step traces back to one or more scenarios in its slice.

**Filter `LOW_VALUE` findings out of the work streams.** A gap classified `LOW_VALUE` by `/specs` or `/test-health` (no branching logic, no observable outcome, coverage already provided by a higher-layer test) never becomes a slice or a TDD step. List such findings in a `## Skipped (low value)` section with their one-line rationale so the decision is visible — they document why the work was *not* planned, not deferred work to revisit. **The plan gate rejects any slice or step classified `LOW_VALUE`**: if a `LOW_VALUE` finding has leaked into a work stream, move it to the Skipped section before the human gate.

### 3. Create the plan

Write the plan file using the structure in `references/plan-template.md` (goal,
acceptance criteria, per-slice Gherkin + TDD steps, parallelization DAG, complexity
classification, pre-PR gate, skipped-findings, risks, and the machine-parseable
Build Progress section).

#### Resolve the Gherkin persistence decision

Follow `references/gherkin-persistence.md`: honor a re-run's recorded
decision, otherwise detect the project's BDD convention
(`scripts/detect_bdd_convention.py`, conservative precedence), prompt once —
or log a skip when non-interactive — and record + echo the resulting
`**Gherkin persistence**:` metadata line (destination directory only). No
`.feature` file is written before approval.

### 4. Create the plans directory

Create `plans/` if it doesn't exist. When writing the plan file, populate the `## Build Progress` section by copying slice and step titles from `## Slices`. These are the checkboxes `/build` will update on disk as each step completes — a slice is checked off once all its steps are. Acceptance Criteria live only in the top-level `## Acceptance Criteria` section as PR-checklist material; the operator ticks each one at PR review time after behaviorally verifying it, not during build.

Then derive the waves — never hand-author them:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plan_waves.py <plan-file>
```

Render the `## Parallelization` Mermaid DAG + wave table and the wave-grouped
`## Build Progress` from its JSON (`waves`, per-slice `wave`). If it exits non-zero
(cycle, missing `Depends-on`, or unknown reference) or reports a `collisions` entry,
fix the plan and re-run before the human gate — those defeat safe concurrent build.

**`scope_mismatches` (#865) is fix-or-acknowledge, not fix-before-gate.** For a slice
declaring slice-level `**Files:**`, this JSON array compares it against the union of
the slice's per-step `**Files**:` lines (`under_declared`/`over_declared`, `[]` when
matching or undeclared). Unlike `collisions`, don't block on it — surface it at the
human gate (step 6); if the author proceeds unreconciled, record it in `## Risks &
Open Questions`.

### 5. Run plan review personas

Before presenting to the user, dispatch the plan review personas in parallel as sub-agents. Each critically challenges the plan from a different perspective. **The reviewer set scales to plan complexity** — a one-function plan does not pay the same review ceremony as a complex feature (the fixed-overhead cost the TDD experiment surfaced; see `docs/experiments/01-final-results.md`).

#### 5a. Classify the plan tier

Derive a **plan tier** from objective signals already on hand — the same `trivial | standard | complex` vocabulary `/build` uses for per-step review depth, so the concept is consistent across the pipeline. Inputs: the slice count and wave structure from the `scripts/plan_waves.py` JSON, the file count, the per-step Complexity ratings, and whether the plan takes a stance on any high-reversal-cost axis in `knowledge/decision-defaults.md`.

| Tier | Signals | Reviewers |
| ------ | --------- | ----------- |
| `trivial` | 1 slice, ≤ 2 files, no `complex` step, touches no high-reversal-cost decision axis | **Acceptance Test Critic only** (1) |
| `standard` | anything between — e.g. a single slice with a few files, or a small multi-slice plan within existing patterns | **Acceptance Test Critic + Design & Architecture Critic**, plus **UX Critic** if the plan has a user-facing/UI surface, plus **Parallelization Critic** if slice count > 1 (2–4) |
| `complex` | > 1 wave, ≥ 4 slices, any `complex` step, a security-sensitive/cross-cutting change, or a **non-default** stance on a high-reversal-cost decision axis, or the axis was **contested** at the `/ship` gate | **all 5** |

Every `/ship`-driven plan states a stance on the axes in `knowledge/decision-defaults.md` — merely restating the default is not, by itself, a `complex` signal (treating it as one would defeat the tier system's own review-scaling goal). "Contested" means a recorded objection to the stance, e.g. a note in the plan's `## Risks & Open Questions` section — not an unrecorded verbal disagreement.

**Worked example** (`Integration: auto-merge vs. direct-to-trunk` axis): a plan stating "open a PR and use auto-merge gated on green checks" (the documented default) does not trigger `complex` on this signal alone. A plan stating "merge directly to trunk, bypassing the PR gate" (a non-default stance) does trigger `complex`, as does a plan stating the default stance where a reviewer's recorded objection challenges it.

When in doubt, classify up (standard rather than trivial, complex rather than standard).

**Parallelization Critic gate (all tiers):** the Parallelization Critic only finds same-wave file collisions and disjoint-file coupling — a **single-slice plan has no waves to parallelize and no same-wave collisions by construction**, so it is a guaranteed no-op there. Run it **only when slice count > 1**, regardless of tier, and log the skip (`Parallelization Critic skipped — single-slice plan`) when it is omitted.

#### 5b. Dispatch the selected reviewers

The personas are subagent **prompt templates** (no frontmatter), dispatched directly via the Agent tool's own `model:` parameter — an alias the harness resolves natively (ADR 0026; no plugin-side resolution step). Pass `model: sonnet` on each persona dispatch; do not hard-code a different model without reason.

| Reviewer | Template | Model | Focus |
| ---------- | ---------- | -------- | ------- |
| Acceptance Test Critic | `${CLAUDE_PLUGIN_ROOT}/prompts/plan-review-acceptance.md` | `sonnet` | Per-slice Gherkin quality (determinism, isolation, implementation-independence), scenario gaps, error paths, criteria coverage, TDD traceability |
| Design & Architecture Critic | `${CLAUDE_PLUGIN_ROOT}/prompts/plan-review-design.md` | `sonnet` | Coupling, abstractions, structural risks, pattern adherence |
| UX Critic | `${CLAUDE_PLUGIN_ROOT}/prompts/plan-review-ux.md` | `sonnet` | User journey, error UX, cognitive load, accessibility |
| Strategic Critic | `${CLAUDE_PLUGIN_ROOT}/prompts/plan-review-strategic.md` | `sonnet` | Problem fit, scope, slice boundaries, risk, opportunity cost |
| Parallelization Critic | `${CLAUDE_PLUGIN_ROOT}/prompts/plan-review-parallelization.md` | `sonnet` | Same-wave independence: file-overlap collisions (from `scripts/plan_waves.py`), disjoint-file behavioral coupling, residual cycles/mis-layering |

Pass each reviewer the full plan content. Also pass the Parallelization Critic the `scripts/plan_waves.py` JSON for this plan (its `collisions` array is the deterministic input). Each returns a structured verdict (`approve` or `needs-revision`) with issues. The Acceptance Test Critic is the gate for the scenarios authored in step 2 — it validates the per-slice Gherkin the same way `feature-file-validation` would, so no separate scenario-review pass is needed before the human gate. It is the one reviewer that always runs (every tier). A `needs-revision` from the Parallelization Critic triggers plan revision (re-wave the colliding slices) before the human sees the plan.

**If any reviewer returns `needs-revision`**: Address all `blocker` issues by revising the plan. Re-run only the reviewers that flagged blockers. Repeat until all pass (max 2 iterations — escalate to user if still failing).

**After all pass**: Append a `## Plan Review Summary` section to the plan file with the aggregated findings (warnings and observations from the dispatched reviewers). **Record the chosen tier and the reviewer set at the top of that section** (e.g. `Plan tier: standard — reviewers: Acceptance, Design, Parallelization (UX skipped — no UI surface)`) so the scaling decision is visible and auditable.

### 6. Present for approval

**Gate check before presenting.** Verify the `## Skipped (low value)` section captures every `LOW_VALUE` finding — no slice or TDD step may carry one. If a `LOW_VALUE` finding leaked into a work stream, move it to the Skipped section before the plan reaches the human.

**Surface any `scope_mismatches` (#865)** alongside the review summary, same visibility as `collisions` — never blocking. Unreconciled on approval → append it to `## Risks & Open Questions`.

**First determine interactivity.** The run is **non-interactive** when any of these hold: `--yes` was passed, `DEV_TEAM_AUTO_APPROVE=1` is set in the environment, or stdin is not a usable TTY (`test -t 0` is false — the headless/CI/automation case). Otherwise it is **interactive**. This is the same non-interactive principle the GitHub-issue prompt below already follows; the approval gate now follows it too, so a headless `/plan`→`/build` run never hangs waiting for input.

- **Interactive** (unchanged from prior behavior) → Display the plan and the review summary. Ask: "Approve this plan to begin implementation, or suggest changes?" Mark the plan status as `approved` once the user confirms. If the user requests changes, update the plan and re-present. This is the Phase 2→3 gate: append an `approval` entry to `metrics/config-changelog.jsonl` per the [human-oversight-protocol § Audit trail](../human-oversight-protocol/SKILL.md#audit-trail) schema — `proposed` names the plan (e.g. "Approve plan for <task>"), `evidence_shown` points at the plan file (and any spec artifact), `risks_surfaced` lists the plan's `## Risks & Open Questions` items (`[]` if none).
- **Non-interactive** → do **not** prompt or block. Auto-approve: set `**Status**: approved` and append an explicit audit record to the plan so the bypass is **never silent** — add an `## Approval` section reading: `Auto-approved (non-interactive) at <date> — no human review gate. Trigger: <--yes | DEV_TEAM_AUTO_APPROVE=1 | no TTY>.` Then continue, appending the same three-field `metrics/config-changelog.jsonl` entry; `description` states the bypass trigger.

#### Post-approval: persist the Gherkin (`.feature` export)

If the plan's recorded `**Gherkin persistence**:` decision is a destination
directory, run the export **from the repo root** (destinations resolve against
the invocation cwd):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plan_gherkin_export.py <plan-file>
```

Show its summary (destination, files written, overwritten, stale removed) to
the operator. The `<dir>/<plan-slug>/` subdirectory is tool-owned — anything
inside is derived and overwritable; files outside it are never touched.
A non-zero exit is a failure: report it with the script's stderr — never claim
success on a failed export. `plan-file-only` decisions skip cleanly (the
script no-ops with a note).

#### Post-approval: offer GitHub issues (GitHub origin only)

After approval, classify the origin remote — **only** offer issue creation on an actual GitHub host:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/git_origin_host.py
```

- **`github`** → prompt **once**, showing the count: *"Open 1 parent issue and N linked slice issues from this plan? [y/N]"* (N = number of slices). The default is **No**. Invoke `/issues-from-plan` **only on explicit `y`**; on No (or anything else), create nothing and continue.
- **`other`** (non-GitHub host, including lookalikes like `notgithub.example.com`) or **`none`** (no origin) → **no prompt**; continue silently.
- **Non-interactive** (`/plan` run without a usable TTY) → do **not** prompt or block: log *"skipping the GitHub issue prompt (non-interactive)"* and continue.

Never create issues without an explicit `y` on an interactive GitHub-origin prompt.

## Integration

- The progress-guardian agent tracks step completion against this plan
- `/continue` reads active plans to resume work
- The orchestrator's Phase 2 produces plans in this same format for larger tasks
