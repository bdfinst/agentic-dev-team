# Top-level Workflows

Two slash commands in this plugin are **orchestrator-only**: they do not
implement, review, or merge anything themselves — they sequence other skills
and agents through their phases, holding the human gates between them.

- [`/ship`](#ship) — spec → plan → build → review → PR, end-to-end.
- [`/test-modernize`](#test-modernize) — five-phase legacy-test modernization
  for CD, from assessment to quality-target convergence.

Both follow the same orchestrator contract: delegate every phase to the
owning skill or agent, honor human gates, surface ambiguous inputs in one
batch up front, and report outcomes concisely.

---

## `/ship`

**File:** [`skills/ship/SKILL.md`](../skills/ship/SKILL.md)
**Role:** orchestrator.
**Use when:** the user says "ship this", "take this feature end to end", or
wants the spec → plan → build → PR flow without re-assembling it each time.

### Steps

| # | Step | Delegates to | Human gate after? |
| --- | --- | --- | --- |
| 1 | **Approach contract** — screen request against [`knowledge/decision-defaults.md`](../knowledge/decision-defaults.md); resolve ambiguous high-reversal-cost axes in one batch. | (orchestrator only) | yes, if a blocker remains |
| 2 | **Spec** *(skipped with `--skip-spec`)* — produce Intent, Architecture, Acceptance Criteria. | [`/specs`](../skills/specs/SKILL.md) | **yes** — operator approves the spec |
| 3 | **Plan** — decompose into vertical slices with Gherkin scenarios; a tier-scaled set of plan-review personas (1–5, by plan complexity) runs in parallel before the gate. | [`/plan`](../skills/plan/SKILL.md) | **yes** — operator approves the plan |
| 4 | **Build** — RED-GREEN-REFACTOR per slice, inline review checkpoints, verification evidence. Do not proceed until the suite is green. | [`/build`](../skills/build/SKILL.md) | no |
| 5 | **Review** — run quality-review agents and let the auto-fix loop converge. Only judgment-call findings escalate to the operator. | [`/code-review`](../skills/code-review/SKILL.md) | no |
| 6 | **PR** — pre-PR quality gate, open PR, arm auto-merge by default (`--no-auto-merge` to opt out). | [`/pr`](../skills/pr/SKILL.md) | **yes** — the PR is the final review artifact |
| 7 | **Report** — PR URL, quality-gate result, whether auto-merge is armed. | (orchestrator only) | — |

### Agents involved (dispatched by the delegated skills)

`/build`'s inline review checkpoints dispatch the review agents listed in
[`team-structure.md` → Review Agent Dispatch](team-structure.md#review-agent-dispatch-phase-3-inline-checkpoints).
`/plan` dispatches a tier-scaled subset of the five plan-review personas
([`prompts/plan-review-*.md`](../prompts/)) — the Acceptance Test Critic always
runs; the rest are added as the plan's tier (`trivial`/`standard`/`complex`)
warrants — and the
[`progress-guardian`](../agents/progress-guardian.md) gate-keeper.
`/code-review` re-runs the same review agents over the full changeset.

### Arguments

`/ship <feature-description> [--skip-spec] [--no-auto-merge]`

### Notes

- Sequencing only — every gate, fix loop, and evidence requirement comes from
  the underlying skills. If any phase stops at a gate, `/ship` stops with it.
- For a plan-only pass, use [`/plan`](../skills/plan/SKILL.md);
  for build-only, use [`/build`](../skills/build/SKILL.md).
- Resume across sessions with [`/continue`](../skills/continue/SKILL.md).

---

## `/test-modernize`

**File:** [`skills/test-modernize/SKILL.md`](../skills/test-modernize/SKILL.md)
**Role:** orchestrator.
**Use when:** a legacy repository needs its tests modernized for CD —
coverage ≥ 90%, zero surviving mutants, full determinism, fastest achievable
pre-merge wall-clock.

Each phase writes a progress file to `memory/test-modernize/<repo-slug>/phase-<n>.md`
so [`/continue`](../skills/continue/SKILL.md) and `--from-phase <n>` can resume.

### Phases

#### 0. Approach contract

Orchestrator only. Resolve `<repo-path>`, the parent issue URL (and the
tracker CLI it maps to: `gh` / `az boards` / `glab` / `acli`, or local-files
mode when empty), CI config, external test sources, quality targets, and the
test-binding mode for the approved Gherkin (`bdd-runner` or
`xunit-with-annotations`). Record the choices in
`memory/test-modernize/<slug>/phase-0.md`.

#### 1. Analyze

Assess the repo against CD test-architecture criteria and emit phase issues.

| Step | Delegates to |
| --- | --- |
| 1.1 Assessment | [`/cd-test-architecture`](../skills/cd-test-architecture/SKILL.md) |
| 1.2 Parent + Phase-1/2/5 child issues | [`/issues-from-assessment`](../skills/issues-from-assessment/SKILL.md) |
| 1.3 Phase gate review | Agent [`dev-team:test-modernization-review`](../agents/test-modernization-review.md) with `--phase 1` |

**Human gate** — approval before specifying the public interface.

#### 2. Specify public interface (two-pass)

Two-pass design so Stories never bind to un-reviewed scenarios.

| Step | Delegates to |
| --- | --- |
| 2.A Author `.feature` files for every public surface (API endpoint, UI flow, batch-job entry point, library export, event type) | [`/gherkin-public`](../skills/gherkin-public/SKILL.md) |
| 2.A.2 Phase gate review | Agent [`dev-team:test-modernization-review`](../agents/test-modernization-review.md) with `--phase 2` |
| **Human gate** — operator validates the Gherkin (hard stop; `.feature` files may be edited in place) | |
| 2.B `--create-stories` — one `[Component tests] <component> · <surface>` Story per approved surface, scenario→Story map written to `gherkin-bindings.json`; backfill Phase-1 placeholders | [`/gherkin-public`](../skills/gherkin-public/SKILL.md) |

#### 3. Audit + baseline coverage

| Step | Delegates to |
| --- | --- |
| 3.1 Disable cannot-fail tests (skip + tag, never delete) | [`/test-audit-disable`](../skills/test-audit-disable/SKILL.md) |
| 3.2 Capture baseline coverage and post to parent issue / `FEATURE.md` | [`/coverage-baseline`](../skills/coverage-baseline/SKILL.md) |
| 3.3 Phase gate review | Agent [`dev-team:test-modernization-review`](../agents/test-modernization-review.md) with `--phase 3` |

**Human gate** — baseline accepted before adding tests.

#### 4. Fix disabled tests + add no-refactor tests

For each Phase-4 child issue in dependency order:

| Step | Delegates to |
| --- | --- |
| 4.1 Drive RED-GREEN-REFACTOR per Story. `[Component tests]` Stories bind tests to the cited `<feature-file>::<scenario-name>` pairs using the Phase-0 binding mode; `[Baseline]` Stories lock in current behavior at existing seams. | [`/build`](../skills/build/SKILL.md) |
| 4.2 After each Story closes, post Δ vs. baseline AND run scoped mutation against the Story's `--story-files` (production-code files from `/build`'s commit diff; tests filtered) | [`/coverage-delta`](../skills/coverage-delta/SKILL.md) `--story <id> --story-files <files>` |
| 4.2b On `status: net_new_survivors`, surface halt prompt with three operator actions (`[s]` strengthen / `[f]` follow-up — drafts Phase-5 `[Strengthen assertions]` Story / `[w]` waive). On `status: tool_unavailable`, triage with `[i]` install via `/init-dev-team` / `[k]` skip — proceed advisory / `[q]` quit. | (orchestrator — owns the halt; worker exit code is always 0) |
| 4.3 After all Phase-4 Stories close, verify scenario→Story-id map against submitted test code | Agent [`dev-team:test-modernization-review`](../agents/test-modernization-review.md) with `--phase 4` |
| 4.4 End-of-phase test review: dispatch `/test-design --since <phase-4-base-sha>` AND `/code-review --since <phase-4-base-sha>`. On error/warning findings, dispatch `/apply-fixes`; re-run `/code-review`; loop max 2 iterations before escalating with `[r]`/`[w]`/`[q]`. Evidence persisted to `phase-4-review.json`. | [`/test-design`](../skills/test-design/SKILL.md) + [`/code-review`](../skills/code-review/SKILL.md) + [`/apply-fixes`](../skills/apply-fixes/SKILL.md) |

**Human gate** — Δ-coverage AND Phase-4 mutation results AND `phase-4-review.json` (any waivers explicit) accepted before any production-code refactor.

#### 5. Refactor-for-testability + converge

For each Phase-5 child issue in dependency order:

| Step | Delegates to |
| --- | --- |
| 5.1 Confirm matching `[Baseline]` Story is closed and green (precondition) | (orchestrator only) |
| 5.2 Minimum behavior-preserving refactor + the test the new seam unblocks | [`/build`](../skills/build/SKILL.md) |
| 5.3 Loop until coverage / mutants / determinism / pre-merge wall-clock targets are met (or explicitly waived with reason recorded). Reads `mutation-history.json` (written by Phase 4) and reuses per-file survivor counts when the file's last commit pre-dates the history entry — re-measures only the gaps. | [`/quality-targets-converge`](../skills/quality-targets-converge/SKILL.md) |
| 5.4 Phase gate review | Agent [`dev-team:test-modernization-review`](../agents/test-modernization-review.md) with `--phase 5` |
| 5.5 End-of-phase test review: same loop as 4.4, scoped to `<phase-5-base-sha>`. Evidence persisted to `phase-5-review.json`. | [`/test-design`](../skills/test-design/SKILL.md) + [`/code-review`](../skills/code-review/SKILL.md) + [`/apply-fixes`](../skills/apply-fixes/SKILL.md) |

**Human gate** — final metrics AND `phase-5-review.json` accepted (or each gap waived with reason).

#### 6. Report

Final coverage %, surviving mutants, determinism status, pre-merge wall-clock,
the parent issue URL (or `./plans/test-modernize/FEATURE.md`), the list of
PRs `/build` opened in Phases 4 and 5, and any waived targets with reasons.

### Agents involved

- [`dev-team:test-modernization-review`](../agents/test-modernization-review.md)
  — phase gate-keeper. Reads each phase deliverable from
  `memory/test-modernize/<repo>/phase-<n>.md` and verifies it matches the
  phase's acceptance criteria before the workflow advances. **Process
  gate-keeper, not a code reviewer — not in the standard review-dispatch
  fan-out.**
- The review agents dispatched by `/build`'s inline checkpoints (same set
  `/ship` uses) — see
  [`team-structure.md` → Review Agent Dispatch](team-structure.md#review-agent-dispatch-phase-3-inline-checkpoints).

### Arguments

`/test-modernize <repo-path> [--parent <issue-url>] [--ci <path>] [--external-tests <loc>] [--from-phase <n>]`

### Notes

- Sequencing only — every gate, fix loop, and evidence requirement comes from
  the underlying skills.
- For Phase-1-only analysis without committing to the full workflow, invoke
  [`/cd-test-architecture`](../skills/cd-test-architecture/SKILL.md) directly.
- The workflow is identical whether or not a tracker CLI is installed — only
  the destination of the issues changes (tracker vs. `./plans/test-modernize/`).
- The operator-facing diagram lives at
  [`diagrams/test-modernize-flow.svg`](diagrams/test-modernize-flow.svg) and
  is embedded in [`agent-architecture.md`](agent-architecture.md#test-modernization-workflow).

---

## Why these are documented together

`/ship` and `/test-modernize` are the only two **multi-phase pipelines with
inter-phase human gates** in the plugin. Every other slash command is either
a single-step worker (e.g. `/coverage-baseline`, `/triage`) or a one-shot
orchestrator that returns in a single pass (e.g. `/code-review`,
`/test-design`). Knowing the phase order, the owning skill or agent for each
step, and where the human gates fall is the difference between operating
these workflows confidently and re-reading every SKILL.md each time.
