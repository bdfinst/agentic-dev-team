# Spec: dev-team Plugin Improvements from the TDD Experiment

**Program of 3 epics** (priority tiers P1/P2/P3), each an independently shippable
improvement surfaced by [`docs/experiments/3sizes-3arms-report.md`](../experiments/3sizes-3arms-report.md)
and [`tdd-vs-nontdd-report.md`](../experiments/tdd-vs-nontdd-report.md).

**Scope note (Scope Split Protocol):** these are **independent** features, not one
feature in slices, so they are split into three epics. Within each epic the
"planned slices" are the deliverable sub-tasks; per-slice Gherkin is authored when
that slice goes through `/plan`. No implementation until each epic's consistency
gate passes.

**Evidence base:** review-grade lens found test-first drew the most findings,
concentrated in `complexity-review` (a REFACTOR-phase gap); review agents showed
run-to-run variance (`naming-review` 0/19/4 on near-identical code);
coverage/mutation saturated and failed to separate quality; the pipeline's fixed
~15–16-turn overhead is a 4.7× tax on small tasks; and a mutation run with no
timeout hung the harness.

---

# Epic P1 — Make review actually improve the code

## Intent Description
Two findings show the review machinery underperforming at its job. First, strict
test-first produced the **most** review findings, concentrated in complexity
(long, deeply-nested functions) — the RED-GREEN-**REFACTOR** loop is stopping at
GREEN, and the purpose-built `refactor-opportunity-review` agent (whose own
description says it runs "after tests pass (TDD REFACTOR phase)") is **never
invoked** by the TDD skill. Second, the review agents are **non-deterministic**:
the same near-identical code drew wildly different findings across runs, which
undermines every `/code-review`. This epic makes the REFACTOR phase enforce
structure, and makes the noisiest review agents repeatable.

## Architecture Specification
- **Components touched:** `skills/test-driven-development/SKILL.md` (§3 REFACTOR);
  `agents/refactor-opportunity-review.md`, `agents/complexity-review.md` (invoked,
  not changed in behavior); `agents/naming-review.md`, `agents/test-review.md`
  (rubric hardening); `skills/agent-eval/` + `evals/expected/` + `evals/fixtures/`
  (new consistency fixtures); `knowledge/agent-registry.md` (if guidance changes).
- **Interfaces/constraints:** REFACTOR must remain a *non-behavioral* step — review
  runs only after tests are green and any auto-fix must keep them green. Review
  agents keep their existing JSON output contract (`{status, issues[], summary}`);
  hardening adds an internal enumerate-then-classify protocol and severity anchors,
  **not** a schema change. Determinism work must not raise per-agent token budget
  past the agent body limits enforced by `/agent-audit`.
- **Dependencies:** the eval harness (`/agent-eval`) must be able to run an agent
  twice on one fixture and compare counts.

## Acceptance Criteria
- AC1: The TDD skill's REFACTOR step dispatches `refactor-opportunity-review` (and
  `complexity-review` when the slice is non-trivial) after GREEN, with a bounded
  fix loop that re-runs tests; documented in the skill body.
- AC2: On the 6 large experiment tasks regenerated test-first, mean
  `complexity-review` findings per solution **drop versus the pre-change baseline**
  (baseline: weighted 32 across 6, i.e. ≈5.3/solution).
- AC3: A consistency eval exists: running `naming-review` (and `test-review`) twice
  on the same fixture yields finding counts within a declared tolerance (e.g. ±1
  finding, identical severity histogram on the canonical fixture); wired into
  `/agent-eval` and CI.
- AC4: `/agent-audit` still passes for every modified agent (body budgets, schema).
- AC5: No behavioral change to production code from a REFACTOR review is allowed to
  leave tests red.

## Planned Slices (sub-tasks)
- **P1-S1 — Wire refactor review into TDD REFACTOR.** Edit
  `test-driven-development/SKILL.md` §3 to invoke
  `refactor-opportunity-review`/`complexity-review` post-GREEN with a bounded
  fix-and-recheck loop. *Deliverable:* updated skill + a fixture proving the loop
  triggers and preserves green. (AC1, AC5)
- **P1-S2 — Reduce REFACTOR-grade complexity on a regression set.** Add the 6 large
  tasks (or a subset) as a complexity regression check; demonstrate the post-GREEN
  review lowers complexity findings. *Deliverable:* before/after finding counts.
  (AC2)
- **P1-S3 — Harden `naming-review` determinism.** Add enumerate-then-classify +
  severity anchors with worked examples. *Deliverable:* updated agent + audit
  pass. (AC4)
- **P1-S4 — Harden `test-review` determinism.** Same treatment. *Deliverable:*
  updated agent + audit pass. (AC4)
- **P1-S5 — Consistency eval fixtures.** Add repeat-run consistency fixtures for
  the two agents to `/agent-eval`; gate in CI. *Deliverable:* fixtures + green
  eval. (AC3)

## Consistency Gate
- [x] Intent is unambiguous
- [x] Every behavior/goal maps to an acceptance criterion (REFACTOR→AC1/AC2/AC5; determinism→AC3/AC4)
- [x] Architecture constrains without over-engineering (reuses existing agents/eval harness; no schema change)
- [x] Terminology consistent across artifacts (REFACTOR, review agent, finding, severity)
- [x] No contradictions between artifacts

---

# Epic P2 — Trust the right quality signals

## Intent Description
The experiment showed coverage and mutation **saturate** (100% / 1.0 on
small/medium; a dead heat on large) and **do not separate** code quality, while the
review agents do. Yet the quality gate and "done" criteria lean on coverage as the
quality bar. Separately, `/build` already logs whether each inline review
checkpoint found/fixed anything (`metrics/review-value.jsonl`, #348), but **nothing
analyzes it** — so we cannot tell which checkpoints earn their cost. This epic
re-weights the quality gate toward signals that discriminate, and turns the
review-value log into an actual report that tunes where review runs.

## Architecture Specification
- **Components touched:** `skills/quality-gate-pipeline/SKILL.md` (gate function);
  `skills/harness-audit/SKILL.md` or `skills/cost-report/SKILL.md` (a review-value
  analysis); `skills/performance-metrics/SKILL.md` (schema reference);
  `skills/build/SKILL.md` (only if checkpoint-tiering guidance changes).
- **Interfaces/constraints:** the gate must treat coverage/mutation as
  **necessary-not-sufficient** — add a structure/complexity review pass as a gate
  input without making the gate unbounded (respect the existing max-3 review-
  correction cycles). The review-value analysis is **read-only** over
  `review-value.jsonl`; it must honor the existing privacy boundary (counts/outcomes
  only, never code). No new telemetry fields unless justified.
- **Dependencies:** `review-value.jsonl` must already be populated by `/build`
  (it is). Analysis needs ≥1 real build's worth of rows to be meaningful.

## Acceptance Criteria
- AC1: The quality gate explicitly states coverage/mutation are necessary-not-
  sufficient and requires a clean-or-triaged `structure-review`+`complexity-review`
  pass (or an explicit waiver) before "done".
- AC2: A command (`/harness-audit` or `/cost-report`) reports per-checkpoint-type
  **fix rate** from `review-value.jsonl` (no-op vs fixed vs escalated), so
  perpetually-no-op checkpoints are identifiable.
- AC3: The analysis emits a concrete recommendation (e.g. "standard-step per-slice
  checkpoint fixed 0/N — candidate to drop") without auto-editing skills.
- AC4: No regression to `/build`'s logging or its privacy boundary (no code/file
  content in the log); verified by existing tests.
- AC5: Gate change does not increase the worst-case review-correction cycle count
  beyond the current cap.

## Planned Slices (sub-tasks)
- **P2-S1 — Re-weight the quality gate.** Edit `quality-gate-pipeline/SKILL.md` so
  the gate requires a structure/complexity review signal alongside coverage/
  mutation, with a waiver path. *Deliverable:* updated gate + example.
  (AC1, AC5)
- **P2-S2 — Review-value fix-rate report.** Add read-only analysis of
  `review-value.jsonl` to `/harness-audit` (or `/cost-report`) producing per-
  checkpoint-type fix rates. *Deliverable:* command output on sample data.
  (AC2, AC4)
- **P2-S3 — Drop-candidate recommendations.** Extend the report to flag always-
  no-op checkpoints as drop candidates; document how to act on them. *Deliverable:*
  recommendation section + docs. (AC3)

## Consistency Gate
- [x] Intent is unambiguous
- [x] Every behavior/goal maps to an acceptance criterion (gate→AC1/AC5; mining→AC2/AC3/AC4)
- [x] Architecture constrains without over-engineering (read-only analysis; reuses existing log + privacy boundary)
- [x] Terminology consistent across artifacts (quality gate, checkpoint, fix rate, review-value)
- [x] No contradictions between artifacts

---

# Epic P3 — Pay plan/review cost only where it earns out

## Intent Description
The `/plan`→`/build` pipeline's fixed ~15–16-turn overhead is a **4.7× tax on
small tasks**, shrinking to 1.3× on large — yet the plan/build tiers are
LLM-self-classified with a "when in doubt, classify **up**" bias that pushes more
ceremony onto exactly the small tasks where it does not pay. And a mutation run
with no wall-clock cap **hung the experiment harness forever** on an infinite-loop
mutant; the shipped `mutation-testing` skill must not have the same gap. This epic
adds an objective size signal that lets trivial work skip planning ceremony, and
hardens mutation execution against hangs.

## Architecture Specification
- **Components touched:** `skills/plan/SKILL.md` and/or
  `skills/context-loading-protocol/SKILL.md` and `agents/orchestrator.md` (size
  gate / no-plan fast path); `skills/mutation-testing/SKILL.md` (timeout).
- **Interfaces/constraints:** the size gate must derive from **objective** signals
  already on hand (changed-file count, function/LOC count, slice/wave JSON), not a
  fresh LLM judgement, and must be **conservative** — only genuinely trivial,
  single-file/single-function work skips `/plan`; everything else keeps the current
  tiered path. The fast path still runs TDD + a final `/code-review` (no
  correctness/quality gate is removed, only the planning ceremony). Mutation
  timeout must treat a timed-out run as a **killed** mutant (matching the harness
  fix already landed) and be tool-appropriate (Stryker/pitest config, or the
  built-in path).
- **Dependencies:** thresholds calibrated from the experiment's per-size cost data
  (`data/3sizes-3arms-summary.json`).

## Acceptance Criteria
- AC1: An objective task-size classifier exists (inputs and thresholds documented),
  reusing the `trivial|standard|complex` vocabulary already shared by `/plan` and
  `/build`.
- AC2: A documented **no-plan fast path** for `trivial` tasks routes straight to a
  single TDD build + final `/code-review`, bypassing the planning personas; the
  decision and its objective inputs are logged.
- AC3: On a representative trivial task, the fast path uses **measurably fewer
  turns/cost** than the full `/plan`→`/build` path, with no loss of the final
  review/correctness gate.
- AC4: `mutation-testing` enforces a per-mutant wall-clock timeout; a timed-out
  mutant counts as killed; documented and, where the tool supports it, set in the
  shipped config.
- AC5: Guardrail — the size gate never downgrades a task that touches a high-
  reversal-cost decision axis (per `knowledge/decision-defaults.md`) to the
  no-plan path.

## Planned Slices (sub-tasks)
- **P3-S1 — Objective size classifier.** Add a deterministic size signal (file/
  function/LOC + slice/wave JSON) feeding the existing tier vocabulary.
  *Deliverable:* classifier spec + thresholds calibrated from cost data. (AC1)
- **P3-S2 — No-plan fast path for trivial tasks.** Wire the classifier into
  `context-loading-protocol`/`orchestrator` so trivial work skips `/plan`; keep the
  final `/code-review`. *Deliverable:* routing change + decision logging.
  (AC2, AC5)
- **P3-S3 — Demonstrate the saving.** Measure turns/cost on a trivial task, fast
  path vs full pipeline. *Deliverable:* before/after numbers. (AC3)
- **P3-S4 — Mutation timeout hardening.** Add a per-mutant timeout (timed-out =
  killed) to `mutation-testing`; verify/set the Stryker/pitest config equivalents.
  *Deliverable:* updated skill + verification note. (AC4)

## Consistency Gate
- [x] Intent is unambiguous
- [x] Every behavior/goal maps to an acceptance criterion (size gate→AC1/AC2/AC3/AC5; mutation→AC4)
- [x] Architecture constrains without over-engineering (objective signals only; conservative gate; no quality gate removed)
- [x] Terminology consistent across artifacts (size tier trivial|standard|complex, fast path, mutant, timeout)
- [x] No contradictions between artifacts

---

## Program verdict

**Consistency gate: PASS for all three epics.** Each is independently specifiable,
internally consistent, and grounded in a named experiment finding with measurable
acceptance criteria. Recommended sequence: **P1 → P2 → P3** (P1 fixes the highest-
leverage, best-evidenced gap; P3 is mostly cost hygiene). Each epic is ready for
`/plan` to slice its sub-tasks into Gherkin-backed increments.
