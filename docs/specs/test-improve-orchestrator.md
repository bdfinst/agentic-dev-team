# Spec: /test-improve orchestrator (consolidation of /test-modernize + /test-upgrade)

<!-- spec-version: 1 -->

**Feature:** Replace `/test-modernize` and `/test-upgrade` with a single `/test-improve` orchestrator that defaults to lightweight ceremony, prompts for heavier capabilities on demand, and always baselines coverage (and mutation, when enabled) before changing any tests.

**Source of truth:** GitHub issue [#536](https://github.com/bdfinst/agentic-dev-team/issues/536).
**Related:** #534 (test-smell-review / advisor remedy division) is in flight as PR #547 — orthogonal to this work.

## Intent Description

`/test-modernize` and `/test-upgrade` answer the same question — *"improve this repo's tests toward CD-alignment"* — from two different ceremony levels, and share 4–5 of the same worker skills. Users have no signal for choosing between them, improvements land twice and drift, and the middle phases converge on the same steps (`/build` + `/coverage-delta` + a mutation check + per-phase review).

`/test-improve` replaces both with one orchestrator that:

1. Defaults to lightweight (upgrade-style) ceremony.
2. Prompts for deeper capabilities — Gherkin extraction, mutation testing, refactor-for-testability phase — only when the operator opts in.
3. Always baselines coverage (and mutation, when enabled) **before** any test changes, so improvement is measurable.
4. Runs code review after every phase (adopting the modernize `3a` end-of-phase review loop).
5. Improves as much as possible **without** production-code refactoring; surfaces refactor-required improvements with rationale and asks whether to run a follow-up phase to tackle them.

`/test-modernize` and `/test-upgrade` are removed in the same PR (no forwarding aliases). Callsites in registries, docs, and worker skills are updated. Two worker skills that hard-code the legacy memory root gain a `--workflow` parameter matching the pattern `coverage-baseline` / `coverage-delta` already use. The `test-modernization-review` agent and its gate script are removed with their orchestrator; the operator-facing flow diagram is redrawn for the new 7-phase shape.

## Architecture Specification

### New surface

**Orchestrator skill:** `plugins/dev-team/skills/test-improve/SKILL.md`

- `role: orchestrator`, `user-invocable: true`.
- 7 phases (0–7 with a conditional Phase 2b and 4b/5) per the issue's canonical layout.
- Memory root: `memory/test-improve/<slug>/`.
- Reports root: `./reports/test-improve/`.
- Plans root: `./plans/test-improve/`.
- Arguments: `<repo-path>` (default cwd), `--parent <url>`, `--analyze-only`, `--from-phase <n>`, `--stack <id>`.
- `allowed-tools`: `Read, Grep, Glob, Bash(git diff *), Skill, Agent` — union of the two parents, minus references to skills being removed.

**New operator-facing diagram:** `plugins/dev-team/docs/diagrams/test-improve-flow.svg` — 7-phase flow, referenced from `plugins/dev-team/docs/workflows.md` and `plugins/dev-team/docs/agent-architecture.md`.

### Phase map (canonical from #536)

| Phase | Action | Worker(s) | Human gate |
|---|---|---|---|
| **0** — Approach contract | Resolve repo path, slug, language(s), stack profile, mutation-on/off, BDD rubric, refactor mode, quality targets, tracker vs local. Persist to `phase-0.md`. | none (interactive) | inline confirmation of resolved inputs |
| **1** — Analyze | Delegate to `/test-health` (which internally calls `/cd-test-architecture` + `/test-design` + `/mutation-testing` when Phase 0 enabled it). | `/test-health` | operator approves the plan; `--analyze-only` exits here |
| **2** — Baseline | Coverage baseline before any test edit. Mutation baseline before any test edit (only if Phase 0 enabled mutation). Records honest score (hard kills / effective total; timeouts separate). Go = advisory only. | `/coverage-baseline --workflow test-improve`, `/mutation-testing --baseline --workflow test-improve` | none (measurement only) |
| **2b** — Derive Gherkin (conditional) | Fires only when Phase-0 BDD rubric returned `bdd-runner` or `xunit-with-annotations`. Reads existing tests + production public surface; writes `.feature` files; in `bdd-runner` mode wires the project's native Gherkin parser (build config, runner dependency, pending step-defs). | `/gherkin-derive --workflow test-improve` | operator reviews `.feature` files (and parser wiring) before any test binds |
| **3** — Triage | Convert health report to work items partitioned by gap class. `NO_REFACTOR` → Phase 4 Stories; `REFACTOR_REQUIRED` → deferred to optional Phase 5; `LOW_VALUE` → advisory-only, never opens PRs to delete tests. | `/issues-from-assessment --workflow test-improve` | operator approves the Phase-4 Story set |
| **4** — Improve without refactoring | For each `NO_REFACTOR` Story: `/build` (tests-only additions, production code read-only) → binding-mode applied → `/coverage-delta --workflow test-improve --story <id>` → mutation improvement via the `mutation-kill` agent (`--file <story-file> --max-rounds 3`, `[c/r/w/q]` halt prompt on residual survivors). Go = advisory-only for mutation. | `/build`, `/coverage-delta`, `mutation-kill` agent | operator approves Δ-coverage + mutation results + `phase-4-review.json` |
| **4** — End-of-phase review loop | After all Phase-4 Stories close: resolve phase base sha; dispatch `/test-design --since <base-sha>` (Farley Score, smells — advisory); dispatch `/code-review --since <base-sha>`; fix loop `/apply-fixes corrections/` → re-run `/code-review`, **max 2 iterations**; iteration-2 failing → `[r/w/q]` escalation; waivers → `waivers.json`; evidence → `phase-4-review.json` (schema: `base_sha`, `head_sha`, `farley_score`, `smells`, `code_review`, `iterations`, `escalated`). | `/test-design`, `/code-review`, `/apply-fixes` | (same gate as above) |
| **4b** — Refactor decision | Surface deferred `REFACTOR_REQUIRED` list with per-item seam + behavior gained + risk. Prompt `[y] yes, run refactor phase / [b] backlog / [q] quit`. | none (interactive) | operator choice IS the gate |
| **5** — Refactor-for-testability (conditional; only on `[y]`) | Refactoring mode = `refactor-allowed`: production-code changes ONLY to introduce a testable seam; existing tests may not be modified or removed; pre-build suite stays green. For each Story: precondition-check Phase-4 baseline Story closed and green → `/build` (min behavior-preserving refactor + the new-seam test) → `/coverage-delta` → mutation-kill loop (same as Phase 4). Then end-of-phase review loop → `phase-5-review.json`. | same as Phase 4 | operator approves refactor results + `phase-5-review.json` |
| **6** — Validate | `/quality-targets-converge --workflow test-improve` loops until all enabled targets are met or each gap is waived on the parent issue / `FEATURE.md`. Mutation disabled = mutation target skipped (not waived). Go = mutation target advisory. Coverage < 90% at end of Phase 6 in no-refactor mode → surface re-run prompt naming backlogged items that would close the gap. | `/quality-targets-converge` | (same as inline waive-or-extend) |
| **7** — Report | Baseline → achieved deltas (coverage line + branch; mutation honest score; determinism; wall-clock). Parent issue URL / `FEATURE.md`. PRs opened by `/build`. Waivers with reasons. Deferred `REFACTOR_REQUIRED` items (if `[b]`). Advisory `LOW_VALUE` removal list. | (report generator) | none |

### Worker-skill changes required

| Skill | Change | Rationale |
|---|---|---|
| `skills/coverage-baseline/SKILL.md` | Add `test-improve` to the recognized values of `--workflow` (skill already parameterized). | Backwards compatible; matches existing multi-workflow pattern. |
| `skills/coverage-delta/SKILL.md` | Same: add `test-improve` to `--workflow`. | Same. |
| `skills/mutation-testing/SKILL.md` + `skills/mutation-testing/references/workflow-callers.md` | Extend the workflow-callers allowlist with `/test-improve` Phase 2 (baseline) and Phase 6 (via `/quality-targets-converge`). Document where workflow-level approval is captured for each. | The allowlist file explicitly requires documentation for each caller. |
| `skills/issues-from-assessment/SKILL.md` | **Add `--workflow` parameter** matching the coverage-{baseline,delta} pattern. Replace hard-coded `memory/test-modernize/<slug>/` and `./plans/test-modernize/` with `memory/<workflow>/<slug>/` and `./plans/<workflow>/`. Default remains `test-modernize` for the removal-transition safety window (which is one PR wide — so this default disappears with the parent). | Skill is currently mono-workflow; consolidation requires it. |
| `skills/quality-targets-converge/SKILL.md` | **Add `--workflow` parameter** the same way. Replace hard-coded `memory/test-modernize/<slug>/` and `./plans/test-modernize/phase-5/` throughout. The Gherkin-binding-gap escape hatch (`[Phase-2 amendment]` Story pointing at `gherkin-bindings.json`) is `/gherkin-public`-tied and is retired with `/test-modernize` — remove it. | Same rationale; the escape hatch has no callers post-removal. |
| `knowledge/skills-registry.md` | Remove `/test-modernize` and `/test-upgrade` rows. Add `/test-improve` row. Update descriptions of worker skills that name their parent orchestrator (`/coverage-baseline`, `/coverage-delta`, `/gherkin-derive`, `/quality-targets-converge`, `/test-audit-disable`). Remove `/gherkin-public` cross-reference if it becomes an orphan (Phase 2b uses `/gherkin-derive` only). | Registry gate (`/agent-audit`) fails on drift. |
| `knowledge/agent-registry.md` | Remove `test-modernization-review` row and update its token-count table row. Remove Test Modernize / Test Upgrade token-count rows. Add Test Improve row. Update `mutation-kill` row's "Relationship" text (was `/test-upgrade`; becomes `/test-improve`). | Same. |
| `knowledge/index.json` | Regenerate (auto-generated). | Auto-generation covers this; not a hand-edit. |
| `plugins/dev-team/docs/skills.md` | Remove `/test-modernize` and `/test-upgrade` rows. Add `/test-improve` row. | Documentation registry. |
| `plugins/dev-team/docs/workflows.md` | Remove the `## /test-modernize` section. Add a `## /test-improve` section (usage, phases, memory paths, resume behavior, tracker vs local). Update the "the only two multi-phase pipelines with…" sentence to name `/test-improve` alongside `/ship`. | `/test-upgrade` was already missing here — consolidation closes that documentation gap. |
| `plugins/dev-team/docs/agent-architecture.md` | Rewrite the `/test-modernize` narrative section for `/test-improve`. Update the embedded diagram reference to `test-improve-flow.svg`. Update the `test-evaluation.md` cross-link. | Operator-facing narrative. |
| `plugins/dev-team/docs/test-evaluation.md` | Replace `/test-modernize` mentions at the "remediation altitude" with `/test-improve`. | Altitude ladder terminology. |
| `plugins/dev-team/docs/team-structure.md` | Remove the `test-modernization-review` special-purpose gate-keeper note. | The gate-keeper is being removed. |
| `README.md` | Update the CLI-tool install-instructions table's `/test-modernize` references to `/test-improve`. | User-facing entry point. |

### Files being deleted (single PR, no aliases)

- `plugins/dev-team/skills/test-modernize/` (whole directory).
- `plugins/dev-team/skills/test-upgrade/` (whole directory).
- `plugins/dev-team/agents/test-modernization-review.md`.
- `plugins/dev-team/scripts/test_modernization_review.py`.
- Any bats tests exclusively covering the four files above (identify via `grep -l test_modernization_review tests/`).
- `plugins/dev-team/docs/diagrams/test-modernize-flow.svg` (replaced by `test-improve-flow.svg`).

### Files not touched (explicit non-scope)

- `plugins/dev-team/skills/test-audit-disable/SKILL.md` — stays user-invocable, unchanged. `/test-improve` does not orchestrate it; teams that want disable-first behavior invoke it directly.
- `plugins/dev-team/skills/gherkin-public/SKILL.md` — retained for direct use even though `/test-improve` uses `/gherkin-derive` only. If it becomes an orphan callsite-wise, a follow-up may remove it (out of scope here).
- `agents/mutation-kill.md` — behavioral spec unchanged. Only the "Relationship to other skills" prose is updated in agent-registry.md.

### Dependency direction and constraints

- **`/test-improve` calls workers; workers do not call `/test-improve`.** No reverse dependency.
- **`/test-health` remains the single-source analyzer.** `/test-improve` does not re-invoke `/cd-test-architecture` or `/mutation-testing` in Phase 1 — the health rollup carries them.
- **Mutation semantics diverge between phases and must stay explicit:** Phase 2 uses `/mutation-testing --baseline` (triage). Phases 4/5 use the `mutation-kill` **agent** (autonomous survivor reduction). Phase 6 uses `/quality-targets-converge` (which itself may re-invoke `/mutation-testing` via the workflow-callers allowlist). The spec fixes this contract; the plan will map each call precisely.
- **Refactor-mode enforcement lives in `/build`.** Phase 4's "production code read-only" and Phase 5's "seam-only" constraints are passed via the same argument shape `/test-upgrade` already used; `/build` honors it. No new mechanism.
- **Human-gate ownership:** Each Phase's gate is the phase's owner. `/test-improve` waits, does not proxy or auto-approve.

## Acceptance Criteria

Every criterion below must be observable — either by inspecting the shipped files, running the orchestrator on a fresh repo, or by a bats/agent-eval fixture.

### Command surface

1. `plugins/dev-team/skills/test-improve/SKILL.md` exists with `user-invocable: true`, `role: orchestrator`, and the 7-phase Steps section matching the phase map above.
2. `plugins/dev-team/skills/test-modernize/` and `plugins/dev-team/skills/test-upgrade/` are absent from `main` after the PR merges. `git log -- plugins/dev-team/skills/test-modernize/ plugins/dev-team/skills/test-upgrade/` shows their removal commits.
3. `plugins/dev-team/agents/test-modernization-review.md` and `plugins/dev-team/scripts/test_modernization_review.py` are absent from `main` after the PR merges.
4. `/agent-audit` passes (registries reflect the removed skills, removed agent, and new orchestrator).

### Phase 0 — Approach contract

1. On a fresh run with no arguments, `/test-improve` prompts (in one batch) for: mutation-on/off (**default off** — lightweight ceremony), BDD rubric (5-question yes/no from `knowledge/references/bdd-value-guide.md`; **default `none`** if the operator declines to answer; ≥3 yes → `bdd-runner` recommended; 1–2 yes → `xunit-with-annotations` recommended), refactor-mode (**default `no-refactor`**), quality targets (defaults: coverage ≥ 90% line + branch, surviving mutants = 0 when mutation enabled, determinism = 100%, wall-clock = fastest achievable), and sink (`--parent` selects tracker; missing CLI falls back to local files). Each prompt displays its default in `[brackets]`; pressing Enter accepts every default in one keystroke.
2. When Go is detected, the operator sees the Go advisory (go-mutesting is alpha-quality; survivor count is not a gate; `go test -fuzz` recommended) before the mutation prompt fires.
3. Phase 0 persists resolved inputs to `memory/test-improve/<slug>/phase-0.md` before Phase 1 starts.
4. `--from-phase <n>` skips completed phases; `--analyze-only` exits after Phase 1.

### Phase 1 — Analyze

1. Phase 1 invokes `/test-health` exactly once; it does not separately invoke `/cd-test-architecture`, `/test-design`, or `/mutation-testing` (those come via the health rollup).
2. When Phase 0 chose mutation-off, the health rollup's mutation section is omitted or marked "not enabled for this run."
3. Human gate: the operator approves the ordered improvement plan before Phase 2 runs.

### Phase 2 — Baseline (before any test change)

1. Coverage baseline lands at `memory/test-improve/<slug>/baseline-coverage.json` before any file under `tests/` (or the stack's test directory) is modified.
2. When mutation is enabled, mutation baseline lands at `memory/test-improve/<slug>/baseline-mutation.json` with the honest score (hard kills / effective total; timeouts separate) before any test change. For Go, the file records the advisory baseline.
3. `/coverage-baseline` and `/mutation-testing --baseline` are both called with `--workflow test-improve`.

### Phase 2b — Derive Gherkin (conditional)

1. When Phase 0's rubric returned `none`, Phase 2b is skipped and no `.feature` files are written.
2. When the rubric returned `xunit-with-annotations`, `.feature` files are written but no runner dependency is added.
3. When the rubric returned `bdd-runner`, the project's native Gherkin parser (cucumber-js / pytest-bdd / behave / cucumber-jvm / SpecFlow / godog per stack profile) is wired in: build config modified, dependency added, pending step-def stubs generated. Surface inventory + parser wiring recorded to `memory/test-improve/<slug>/gherkin.md`.
4. Human gate: operator reviews `.feature` files (and parser wiring in `bdd-runner` mode) before any test binds.

### Phase 3 — Triage

1. `/issues-from-assessment` is invoked with `--workflow test-improve` and writes any Stories to `./plans/test-improve/` (or the configured tracker).
2. Gap classification is partitioned three ways: `NO_REFACTOR` → Phase-4 Stories; `REFACTOR_REQUIRED` → deferred to optional Phase 5 (surfaced but not implemented in Phase 4); `LOW_VALUE` → advisory-only, never opens PRs to delete tests.
3. Human gate: operator approves the Phase-4 Story set and sees the deferred `REFACTOR_REQUIRED` list.

### Phase 4 — Improve without refactoring

1. `/build` refuses to modify any file under the production-code paths in Phase 4 (`no-refactor` mode enforced by `/build`, verifiable by a fixture where a Story asks for a refactor and `/build` rejects it).
2. Binding mode is applied per Phase 0's choice: `none` → plain xUnit; `xunit-with-annotations` → test names mirror scenario names, Given/When/Then in leading comments citing the source `.feature` file; `bdd-runner` → the parser's step-defs are implemented to green.
3. `/coverage-delta --workflow test-improve --story <id>` fires per Story and records the per-Story movement.
4. When mutation is enabled, the `mutation-kill` agent is invoked per Story (`--file <story-file> --max-rounds 3`). On residual survivors, the `[c]ontinue / [r]etry / [w]aive / [q]uit` prompt fires. Go = advisory-only (survivors logged, no commit; operator applies manually).
5. After all Phase-4 Stories close, the end-of-phase review loop runs: `/test-design --since <base-sha>` and `/code-review --since <base-sha>` dispatch in parallel; fix loop `/apply-fixes corrections/` → re-run `/code-review`, max 2 iterations; iteration-2 failing → `[r] revise / [w] waive / [q] quit` escalation; waivers land in `memory/test-improve/<slug>/waivers.json` tagged with the finding list.
6. `memory/test-improve/<slug>/phase-4-review.json` exists with schema `{base_sha, head_sha, farley_score, smells, code_review, iterations, escalated}`.
7. Human gate: operator approves Δ-coverage + mutation results + `phase-4-review.json`.

### Phase 4b — Refactor decision

1. After Phase 4 closes, `/test-improve` prints the `REFACTOR_REQUIRED` list with per-item {seam, behavior gained, risk} columns and prompts `[y] yes, run refactor phase / [b] backlog / [q] quit`. The letter `y` is used deliberately: `r` is claimed by mutation-kill's `[c/r/w/q]` (retry) and the review-loop's `[r/w/q]` (revise) — three phases could not share the same key without operator confusion.
2. `[r]` advances to Phase 5. `[b]` writes `memory/test-improve/<slug>/refactor-backlog.md` (or updates the parent issue) and skips to Phase 6. `[q]` skips to Phase 6 immediately.

### Phase 5 — Refactor-for-testability (conditional)

1. Phase 5 runs only when the operator picked `[r]` at Phase 4b. Otherwise the phase is absent from the run log.
2. `/build` under Phase 5 permits production-code changes ONLY to introduce a testable seam; existing tests may not be modified or removed; the pre-build suite stays green throughout (verifiable via `/build`'s existing green-suite check + a fixture where the plan tries to delete an existing test and is rejected).
3. Precondition-check: for each Phase-5 Story, the matching Phase-4 baseline Story is closed and green before the refactor begins.
4. End-of-phase review loop runs the same as Phase 4. `memory/test-improve/<slug>/phase-5-review.json` exists.
5. Human gate: operator approves refactor results + `phase-5-review.json`.

### Phase 6 — Validate

1. `/quality-targets-converge --workflow test-improve` runs and writes any Stories to `./plans/test-improve/`.
2. If Phase 0 disabled mutation, the mutation target is **skipped** (not waived) in Phase 6.
3. If the stack is Go, the mutation target is advisory only.
4. When Phase-6 exits with coverage < 90% and refactor mode was `no-refactor` (Phase 5 skipped), `/test-improve` surfaces the "re-run and choose refactor-allowed" prompt `[y] re-run in refactor-allowed mode / [n] accept current coverage` naming the backlogged `REFACTOR_REQUIRED` items that would close the gap. Same prompt fires when coverage ≥ 90% but the mutation target is missed in no-refactor mode and one or more backlogged items would close the mutation gap.

5. **Phase-start banner.** At the start of each phase (0–7), `/test-improve` prints a one-line banner `Phase N/7 — <name>` followed by a one-line recap of the still-active Phase-0 settings (`mutation: on|off · binding: <mode> · refactor: <mode> · sink: <tracker|local>`). Operators resuming via `--from-phase` or returning to a long-running session see the current phase and active settings without scrollback archaeology.

6. **Phase-0 answers are immutable for the remainder of the run.** `--from-phase` does not re-prompt Phase-0 inputs; to change them, delete `memory/test-improve/<slug>/phase-0.md` and re-run from Phase 0.

### Phase 7 — Report

1. Final report is generated from the shipped template at `plugins/dev-team/skills/test-improve/templates/executive-summary.md` and written to `reports/test-improve/<repo-slug>-<date>.md`. Every placeholder is interpolated from persisted memory files under `memory/test-improve/<slug>/` — the report is regeneratable from those files after the fact.

2. Report contains all 10 numbered sections from the template: (1) Bottom line + baseline/achieved/Δ metrics table; (2) What was done this run + PRs opened; (3) What was measured (baseline + final file paths); (4) `/test-health` findings (Farley Score, quadrant coverage, architecture summary); (5) Phase-4 work completed (`NO_REFACTOR` Stories); (6) Phase-5 work completed (`REFACTOR_REQUIRED` Stories) OR "Phase 5 not run — operator chose to backlog…"; (7) Deferred work (backlogged `REFACTOR_REQUIRED`, advisory `LOW_VALUE` removals, coverage gap analysis); (8) Waivers with reasons; (9) Next actions (ordered by leverage); (10) Provenance links.

3. Sections with no data render `_Not applicable — <reason>._` — they never disappear. This keeps the report shape stable across runs so operators (and later AI sessions) find the same information in the same place regardless of which mode ran.

4. When the run used a `--parent <url>` tracker, the parent issue is updated with a link to the report file. When the run used local files only, `plans/test-improve/FEATURE.md` is updated with the same link.

5. Numbers always show baseline → achieved → Δ. Never just "final coverage: 87%". The delta is the story.

6. Go advisory footnote surfaces on the mutation row of § 1 whenever the language is Go, regardless of whether mutation was enabled.

### Worker-skill parameterization

1. `skills/issues-from-assessment/SKILL.md` accepts `--workflow <name>` and routes memory + plan paths to `memory/<workflow>/<slug>/` and `./plans/<workflow>/`. Default value is documented (either `test-improve` outright, or a chosen safe default with a bats test asserting `/test-improve` passes `test-improve` explicitly).
2. `skills/quality-targets-converge/SKILL.md` accepts `--workflow <name>` and does the same. The `[Phase-2 amendment]` escape hatch is removed (it was `/gherkin-public`-tied).
3. `skills/mutation-testing/references/workflow-callers.md` adds `/test-improve` Phase 2 and Phase 6 entries with the workflow-level approval capture-point documented for each.
4. `skills/coverage-baseline` and `skills/coverage-delta` recognize `test-improve` as a valid `--workflow` value (documented in their SKILL.md; no code change beyond the enum/documentation).

### Documentation and diagrams

1. `plugins/dev-team/docs/diagrams/test-improve-flow.svg` exists and is referenced from `plugins/dev-team/docs/workflows.md` and `plugins/dev-team/docs/agent-architecture.md`.
2. `plugins/dev-team/docs/workflows.md` contains a `## /test-improve` section (usage, phases, memory paths, resume behavior) and no `## /test-modernize` section. The "only multi-phase pipelines" sentence names `/test-improve` (alongside `/ship`), not `/test-modernize`.
3. `plugins/dev-team/docs/agent-architecture.md`, `plugins/dev-team/docs/skills.md`, `plugins/dev-team/docs/test-evaluation.md`, `plugins/dev-team/docs/team-structure.md`, and `README.md` reference `/test-improve` where they previously named `/test-modernize` or `/test-upgrade`; no live callsite mentions the removed commands.
4. `knowledge/skills-registry.md` and `knowledge/agent-registry.md` are updated per the Worker-skill changes table.
5. `knowledge/index.json` regenerates cleanly (`/agent-audit` passes).

### Structural gates

1. `/agent-audit` passes (all frontmatter valid; registry current; no dangling references to removed skills/agent).
2. `/agent-eval` passes for `test-improve` (at least a Phase-0 fixture asserting the resolved-inputs block, and a `--from-phase` skip fixture).
3. `tests/skills/` gains bats coverage for: (a) `/test-improve` Phase-0 prompt battery, (b) `--workflow test-improve` routing in `issues-from-assessment` and `quality-targets-converge`, (c) the Phase-4b `[r/b/q]` prompt shape, (d) the Phase 5 "existing test may not be modified" refusal, (e) the coverage-<90% no-refactor Phase-6 re-run prompt.
4. `tests/repo/knowledge_index_current.bats` and `tests/repo/skills_index_current.bats` (or their current equivalents) pass — no stale registry rows.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| Fate of `/test-modernize` and `/test-upgrade` — aliases, remove immediately, or keep forever? | `requires-stakeholder-input` | human | Remove immediately in the same PR. No forwarding aliases. |
| Command name — `/test-improve` vs `/tests` vs `/test-align`? | `requires-stakeholder-input` | human | `/test-improve`. |
| This `/ship` run's stop point — spec only, spec+plan, or full end-to-end? | `requires-stakeholder-input` | human | Full end-to-end. |
| Fate of `agents/test-modernization-review.md` + `scripts/test_modernization_review.py`? | `requires-stakeholder-input` | human | Remove both. Their Phase 3/4 checks reference artifacts (`disabled-tests.json`, `gherkin-bindings.json`) the new orchestrator never produces. |
| `issues-from-assessment` and `quality-targets-converge` hard-code `memory/test-modernize/…` paths — how to reconcile? | `requires-stakeholder-input` | human | Add `--workflow <name>` parameter to both, matching the pattern `coverage-baseline` / `coverage-delta` already use. `/test-improve` passes `--workflow test-improve`. |
| `plugins/dev-team/docs/diagrams/test-modernize-flow.svg` — redraw or defer? | `requires-stakeholder-input` | human | Redraw as `test-improve-flow.svg` in this PR. |
| Mutation-remediation model — `/test-modernize`'s triage-then-Story-then-/build vs `/test-upgrade`'s autonomous `mutation-kill` agent? | `inferable` | inference | Adopt `mutation-kill` agent for Phases 4/5 (issue's locked-in decision), keep `/mutation-testing` for Phase 2 baseline and Phase 6 via `/quality-targets-converge` (the two allowlisted callers). Explicit in the Architecture Specification. |
| Gherkin-authoring path — `/gherkin-public` (two-pass, tracker-Story-creating) vs `/gherkin-derive` (single-pass)? | `inferable` | inference | Use `/gherkin-derive` only (issue's worker list includes only this; the derivation-from-code framing matches the issue's "extract Gherkin from the code" requirement). `/gherkin-public` is not deleted (out of scope) but has no orchestrated caller after this lands. |
| Disabled-test audit sub-protocol (`test-audit-disable` + `disabled-tests.json` + `repair`/`defer` resolution) — retained in `/test-improve`? | `inferable` | inference | Not retained. The issue's Phase list has no disable phase. `test-audit-disable` remains user-invocable for teams that want it, per the issue's explicit "Not in scope" note. |
| End-of-phase review loop (test-modernize's 3a: test-design + code-review + apply-fixes + max-2-iteration fix loop + waivers + evidence JSON) — kept in `/test-improve`? | `inferable` | inference | Kept (issue's locked-in decision "Adopt modernize's 3a review-the-phase loop after Phase 4 and Phase 5"). |
| Refactor-mode reconciliation — `test-modernize`'s always-refactor Phase 5 vs `test-upgrade`'s `no-refactor` default? | `inferable` | inference | Default `no-refactor` (issue's explicit requirement: "improve as much as possible without refactoring and advise about improvements that will require refactoring and ask if it should do those in another phase"). Phase 5 is conditional on operator opt-in. |
| `allowed-tools` frontmatter allowlist for `/test-improve` — union or intersection of the two parents? | `inferable` | inference | Union minus references to the removed skills (`/test-audit-disable` is user-invocable, not orchestrated; `/gherkin-public` is not called by `/test-improve`). Documented in Architecture Specification. |
| Should `/test-improve` open PRs to delete `LOW_VALUE` tests? | `inferable` | inference | No — issue's locked-in decision "list-only advisory (modernize-style); never auto-delete tests; operator triggers removals manually." |
| Handling `bats` tests that exclusively cover removed files? | `inferable` | inference | Remove alongside their targets (standard cleanup; no policy question). Identify via `grep -l test_modernization_review tests/` and `grep -rl 'skills/test-modernize\|skills/test-upgrade' tests/`. |
| `.dev-team/quality-targets.json` schema doc — extract to standalone? | `inferable` | inference | No — out of scope. Schema stays inline-documented in `quality-targets-converge/SKILL.md` (current shape). A follow-up may extract it. |
| Phase-7 executive-summary template — `/test-improve` ships one or leaves formatting up to each run? | `requires-stakeholder-input` (surfaced during plan review, iteration 1) | issue #536 addendum comment | Ship a fixed 10-section template at `plugins/dev-team/skills/test-improve/templates/executive-summary.md`; Phase 7 copies + interpolates it to `reports/test-improve/<repo-slug>-<date>.md`. Placeholders resolve from `memory/test-improve/<slug>/` files; sections with no data render `_Not applicable — <reason>._` (they never disappear). The parent-issue post (or `plans/test-improve/FEATURE.md`) links to the report. See Architecture Specification § "Phase 7". |
| Phase-4b prompt letter — `[r]` vs `[y]`? | `requires-stakeholder-input` (surfaced during plan review, iteration 1) | human | `[y]`. The letter `r` is already claimed by mutation-kill's `[c/r/w/q]` (retry) and the review-loop's `[r/w/q]` (revise); overloading `r` a third time would produce operator confusion at the highest-consequence prompt in the flow. |
| Phase-6 re-run prompt bracketed shape? | `inferable` (surfaced during plan review) | inference | `[y] re-run in refactor-allowed mode / [n] accept current coverage`. Matches the flow's every-prompt-has-a-bracketed-shape convention. |
| Phase-0 answer immutability under `--from-phase`? | `inferable` (surfaced during plan review) | inference | Phase-0 answers are immutable for the remainder of the run; `--from-phase` does not re-prompt Phase-0 inputs. To change them, delete `phase-0.md` and re-run from Phase 0. Explicit in AC5 and AC8 update. |
| Mutation and BDD-rubric defaults at Phase 0? | `inferable` (surfaced during plan review) | inference | Mutation defaults **off**; BDD rubric defaults to **`none`** when the operator declines to answer. The intent "defaults to lightweight ceremony" implied these but did not state them; the spec now does. |
| Runtime vs prose-only verification of AC50 / AC53(c)(d)(e)? | `inferable` (surfaced during plan review) | inference | Both. Phase-slice bats fixtures verify SKILL.md prose (fast, deterministic, always-run). `/agent-eval` fixtures verify observable runtime behavior for the Phase-0 prompt battery and the `--from-phase` skip. AC53(c)(d)(e) are narrowed to prose-verified with a follow-up issue tracking optional runtime fixtures — runtime verification of the Phase-4b prompt shape and Phase-5 refusal requires driving a full orchestrator run, which is disproportionate to the risk (SKILL.md prose is the runtime contract). |
| Tracker-label templates in `issues-from-assessment` — parameterize too? | `requires-stakeholder-input` (surfaced during plan review) | inference | Yes. The skill hard-codes `test-modernize` in GitHub/GitLab/ADO issue-label strings (`--label`, `System.Tags=`, `labels[]`), not only in filesystem paths. `/test-improve` must parameterize these on `--workflow` too, or operator-visible tracker tags leak `test-modernize` from `/test-improve` runs. Slice 11.1 covers this. |
| `agent-architecture.md` `[Phase-2 amendment]` prose dangling after Slice 11.2? | `inferable` (surfaced during plan review) | inference | Remove the paragraph in Slice 11.2 alongside the SKILL.md removal. Same lockstep principle as the mutation-testing three-way allowlist. |

## Consistency Gate

- [x] Intent is unambiguous — two developers would interpret the shared "consolidate two orchestrators into one, remove the originals, keep the lighter default, gate heavier capabilities behind operator opt-in" story identically.
- [x] Every behavior/goal in the intent maps to at least one acceptance criterion — the phase map's 7 phases → ACs 5–40; worker-skill changes → ACs 41–44; docs/registries → ACs 45–49; structural gates → ACs 50–53.
- [x] Architecture constrains without over-engineering — the spec adds one orchestrator, redraws one diagram, adds a `--workflow` parameter to two skills (matching an existing pattern), removes four files, and updates registry/doc callsites. No new mechanisms, no new frameworks.
- [x] Terminology consistent across artifacts — "Phase 0/1/…/7", "no-refactor mode", "refactor-allowed mode", "`REFACTOR_REQUIRED` / `NO_REFACTOR` / `LOW_VALUE`", "honest mutation score (hard kills / effective total; timeouts separate)", "end-of-phase review loop", "`memory/test-improve/<slug>/`" appear identically in Intent, Architecture, and Acceptance.
- [x] No contradictions between artifacts — mutation model, Gherkin path, refactor mode, review loop, and removal (no aliases) are stated the same way in all three sections.
- [x] Every gap/ambiguity finding is logged — six `requires-stakeholder-input` items resolved by human answers; eight `inferable` items documented with rationale.

**Gate result: PASS.** Proceeding to `/plan`.
