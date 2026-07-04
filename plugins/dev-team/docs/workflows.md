# Top-level Workflows

Two slash commands in this plugin are **orchestrator-only**: they do not
implement, review, or merge anything themselves — they sequence other skills
and agents through their phases, holding the human gates between them.

- [`/ship`](#ship) — spec → plan → build → review → PR, end-to-end.
- [`/test-improve`](#test-improve) — seven-phase consolidated
  analyze-then-improve orchestrator for legacy or in-flight test suites.

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
| 4 | **Build** — small per-behavior batches per slice (code-first default; TDD opt-in), inline review checkpoints, verification evidence. Do not proceed until the suite is green. | [`/build`](../skills/build/SKILL.md) | no |
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

## `/test-improve`

**File:** [`skills/test-improve/SKILL.md`](../skills/test-improve/SKILL.md)
**Role:** orchestrator.

Consolidated analyze-then-improve test orchestrator. Defaults to lightweight
ceremony, prompts for heavier capabilities on demand, and always baselines
coverage (and mutation, when enabled) before any test change.

### Phases

Each phase writes a progress file to
`memory/test-improve/<slug>/phase-<n>.md` so `/continue` (and `--from-phase`)
can resume.

- **Phase 0 — Approach contract.** Batched prompt (Enter accepts all
  defaults): mutation `[off]`, BDD rubric `[none]`, refactor `[no-refactor]`,
  quality targets, sink (`--parent <url>` vs local files). Go stack shows the
  alpha go-mutesting advisory before the mutation prompt. Answers are
  immutable for the run.
- **Phase 1 — Analyze.** Delegate to `/test-health` (sole worker). No
  separate calls to `/cd-test-architecture`, `/test-design`,
  `/mutation-testing`. Mutation section respects Phase-0 setting.
- **Phase 2 — Baseline (before any test edit).**
  `/coverage-baseline --workflow test-improve` unconditionally;
  `/mutation-testing --baseline --workflow test-improve` when mutation is on.
  Go = advisory-only marker. Honest score = hard kills, timeouts separate.
- **Phase 2b — Derive Gherkin (conditional).** `none` skips entirely;
  `xunit-with-annotations` writes `.feature` files without a runner;
  `bdd-runner` wires the native parser.
- **Phase 3 — Triage.** `/issues-from-assessment --workflow test-improve`
  partitions findings into `NO_REFACTOR` (Phase-4 Stories) /
  `REFACTOR_REQUIRED` (deferred to Phase 5) / `LOW_VALUE` (advisory-only).
- **Phase 4 — Improve without refactoring.** Per Story: `/build`
  (no-refactor) → `/coverage-delta --workflow test-improve --story <id>` →
  `mutation-kill` agent (`--file <story-file> --max-rounds 3`, `[c/r/w/q]` on
  residuals). End-of-phase review loop runs `/test-design --since` and
  `/code-review --since` in parallel, `/apply-fixes` then re-run, cap 2
  iterations, `[r/w/q]` escalation. Evidence in `phase-4-review.json`.
- **Phase 4b — Refactor decision prompt.** `[y] enter Phase 5 / [b] backlog
  and skip to Phase 6 / [q] quit`.
- **Phase 5 — Refactor-for-testability (conditional).** Only when `[y]`.
  Seam-only production-code changes; existing tests are immutable. Same
  end-of-phase review loop; evidence in `phase-5-review.json`.
- **Phase 6 — Validate.** `/quality-targets-converge --workflow test-improve`.
  Mutation off = skipped (not waived). Go = advisory-only. Coverage < 90% in
  no-refactor mode → `[y/n]` re-run-in-refactor-allowed prompt lists
  backlogged items.
- **Phase 7 — Executive-summary report.** Interpolates the shipped
  `templates/executive-summary.md` from `memory/test-improve/<slug>/` files
  to `reports/test-improve/<repo-slug>-<date>.md`. 10 numbered sections;
  empty sections render "Not applicable" (never omitted). Parent tracker (or
  `plans/test-improve/FEATURE.md`) is updated with a link to the report.
  Report is regeneratable from memory.

### Invocation

`/test-improve <repo-path> [--parent <url>] [--analyze-only] [--from-phase <n>] [--stack <id>]`

Flow diagram:
[`diagrams/test-improve-flow.svg`](diagrams/test-improve-flow.svg).

---

## Why these are documented together

`/ship` and `/test-improve` are the two **multi-phase pipelines with
inter-phase human gates** in the plugin. Every other slash
command is either a single-step worker (e.g. `/coverage-baseline`,
`/triage`) or a one-shot orchestrator that returns in a single pass (e.g.
`/code-review`, `/test-design`). Knowing the phase order, the owning skill
or agent for each step, and where the human gates fall is the difference
between operating these workflows confidently and re-reading every SKILL.md
each time.

One cross-command lifecycle *is* documented separately: the defect workflow
that connects `/triage`'s triage records, `/code-review`'s correction
prompts, and `/apply-fixes` — from discovery to applied fix, including who
owns leftover `corrections/` files — lives in
[triage-workflow.md](triage-workflow.md).
