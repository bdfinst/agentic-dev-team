# `orchestrator.py` — Script Implementation Notes

`scripts/orchestrator.py` is the `Enforcement: script` deterministic
implementation of the three-phase pipeline. This file records what it actually
dispatches per phase, and every place where it diverges from — or does not yet
implement — the agent-facing policy in
`${CLAUDE_PLUGIN_ROOT}/knowledge/three-phase-workflow.md`.

Read it when running or working on that script. An interactive session following
the phase policy does not need it: everything a divergence leaves unimplemented
is already the operator's own responsibility in that mode.

## Phase 1: Research

**Implementation status.** `orchestrator.py`'s `run_pipeline` dispatches the
Research persona roster below and writes the progress file, then returns —
it does not yet emit a design doc and there is no in-script human gate
between phases. Both remain the operator's own responsibility today (the
interactive session reviews the written research state before continuing to
Phase 2 by hand); tracked against spec #1707 for a future slice.

### Research persona roster (`RESEARCH_PERSONAS`)

`orchestrator.py`'s `_default_phase_research` — the `Enforcement: script`
deterministic implementation of this phase — always dispatches
`codebase-recon`, `architect`, and `data-flow-tracer` for every
`standard`/`complex`-classified task routed to the full three-phase pipeline
(`run_pipeline`'s only classification-driven branch point is the `trivial`
fast-path — `--fail-wave` and `--dispatch-personas` short-circuit earlier
for their own test/debug purposes and are not reachable from a normal
classified run; `--resume` is a separate, operational flag, not test-only —
it exits 1 only when no prior phase state exists at all, and otherwise
falls through to Phase 1 and skips only the phases whose state files are
already present; the single-module `standard` fast-path leg of
`agents/orchestrator.md` § Task Size Gate is not yet implemented by the script, a known gap tracked
against spec #1707);
`security-engineer` is additional and conditional (below). This is the
current, authoritative roster (spec issue #1707's Architecture
Specification); `architect` and `data-flow-tracer` were not previously
listed under Phase 1 because Research dispatch was a stub before that
spec's slices landed.

### Codebase Recon dispatch — script gap

**Script gap.** `orchestrator.py`'s `_default_phase_research` does not yet
implement the freshness gate or the ordering in
`${CLAUDE_PLUGIN_ROOT}/knowledge/three-phase-workflow.md#codebase-recon-dispatch` — it dispatches
`codebase-recon` unconditionally on every `standard`/`complex`-classified
task, concurrently with the other Research personas in one `asyncio.gather`
wave with no barrier, so nothing reads the recon artifact from disk before
`architect`, `data-flow-tracer`, and (when dispatched) `security-engineer`
run — so that ordering guarantee is unmet on the script path too, not
just the freshness gate. Both the freshness check and the ordering /
artifact-bridging into the aggregated Research output are known gaps
tracked against spec #1707's Plan-phase slice, not yet implemented.

### Security Engineer dispatch — script approximation

**Script approximation.** `orchestrator.py`'s `_touches_security` implements
only the first of the dispatch signals in
`${CLAUDE_PLUGIN_ROOT}/knowledge/three-phase-workflow.md#security-engineer-dispatch`, and only partially: a case-insensitive
substring match against `SECURITY_KEYWORDS` (`auth`, `secret`, `crypto`,
`password`, `token`, `credential`, `encrypt`) — a heuristic, not a precise
classifier (deliberate false positives and negatives are documented and
tested). The other three signals — new integration/API surface, a prior
`security-review` fail verdict, and an explicit user request — have no
script implementation yet; a known gap tracked against spec #1707. When
dispatched (by either mechanism), `security-engineer` produces a threat
model or security analysis that feeds into the design doc and the plan's
acceptance criteria.

## Phase 2: Plan

### Plan persona roster (`PLAN_CORE_PERSONAS`)

`orchestrator.py`'s `_default_phase_plan` — the `Enforcement: script`
deterministic implementation of this phase — dispatches a two-stage
sequence for every `standard`/`complex`-classified task: first the core
trio `product-manager`, `architect`, `qa-engineer` (`PLAN_CORE_PERSONAS`),
unconditionally, with the Research phase's aggregated state as context;
then the five `plan-review-*` critics (`DEFAULT_PERSONAS`), against the
core trio's own results as the draft under review — unless every core-trio
result failed, in which case critic dispatch is skipped entirely (an
LLM-cost guard: with no usable draft, the five `claude -p` critic dispatches
would only critique identical failure stubs — a deliberate degraded-path
divergence from the agent-facing policy in
`${CLAUDE_PLUGIN_ROOT}/knowledge/three-phase-workflow.md#phase-2-plan`) and the persisted state
records why (`critics_skipped_reason: "all_core_personas_failed"`).

**Script gap.** The "Automated plan review" bullet in
`${CLAUDE_PLUGIN_ROOT}/knowledge/three-phase-workflow.md#phase-2-plan` describes
reviewer-set scaling by plan tier — that scaling is not implemented by the
script: `_default_phase_plan` always dispatches all five critics
(`DEFAULT_PERSONAS`) unconditionally, with no notion of plan tier in its
persisted state at all. This is a known gap tracked against spec #1707,
not yet implemented.

## Phase 3: Implement

**Implementation status.** `orchestrator.py`'s `run_pipeline` dispatches
this phase via `_default_phase_implement` immediately after Plan completes,
for every `standard`/`complex`-classified task — the same classification-
driven scope Research and Plan already use (the `trivial` fast-path is
`run_pipeline`'s only *classification*-driven branch point; `--fail-wave`,
`--dispatch-personas`, and the no-prior-state `--resume` guard are separate,
test/debug-only early-return paths, not part of this classification logic).
See the Implement persona roster
subsection below for what the script actually dispatches, and its Script
gap paragraph for what the agent-facing policy in
`${CLAUDE_PLUGIN_ROOT}/knowledge/three-phase-workflow.md#phase-3-implement` still describes that
the script does not yet implement.

### Implement persona roster (`SOFTWARE_ENGINEER_PERSONA` / `TECH_WRITER_PERSONA`)

`orchestrator.py`'s `_default_phase_implement` — the `Enforcement: script`
deterministic implementation of this phase — composes two helpers for every
`standard`/`complex`-classified task. `_dispatch_implement_wave` dispatches
`SOFTWARE_ENGINEER_PERSONA` (`software-engineer`) once, for the sole
synthetic slice in `IMPLEMENT_WAVE_SLICES` (`("implement-1",)`), via the
existing `dispatch_personas` (reused verbatim rather than a second
hand-rolled `asyncio.gather`/`BaseException`-normalization copy), with the
Plan phase's aggregated state as context. Each result is tagged with its
`"slice"` key before `reconcile()` runs directly against the wave's results;
a `status: "failed"` entry raises `WaveError`, which propagates uncaught out
of `_dispatch_implement_wave` — `_run_phase`'s `write_progress` call never
runs for a failed wave, so the phase's state file stays absent and a
subsequent `--resume` run retries Implement from scratch. `run_pipeline`
catches `WaveError` at its own call site, prints
`ERROR: wave barrier failed on slice '<failing_slice>'` followed by
`Resume with: python3 <script-path> --resume` (via the shared
`_print_wave_failure` helper, also used by the `--fail-wave` test/debug
simulation branch, which deliberately prints an unrelated `'slice-1'` name
since it doesn't go through `IMPLEMENT_WAVE_SLICES`), and returns exit code
1. The wave's own stderr WARNING (labeled `"Implement"`) uses different
wording than Research/Plan's non-fatal WARNINGs — `(wave barrier will
fail)`, not `(recorded, non-fatal)` — since a wave failure here is neither:
it is about to raise `WaveError` uncaught and end the process.

On a successful wave (no failed slice), `_dispatch_implement_verification`
dispatches the existing `CODE_REVIEW_PANEL` (`doc-review`, `arch-review`,
`token-efficiency-review`) and `TECH_WRITER_PERSONA` (`tech-writer`) — both
via `dispatch_personas`, never a bare `dispatch_persona` call, so an
unexpected throwable from either is normalized into a failure stub instead
of escaping past `run_pipeline`'s `except WaveError` and discarding a
successful wave's results — against the wave's own results as context. Both
dispatches receive the task classification, the original request text, and
the wave's dispatch-result metadata (persona/status/slice per entry) — not
the actual changeset diff or the affected documentation files, so neither
call performs a real code review or doc pass today — narrower than their
names promise, mirroring the same narrowing Phase 2's
`plan-review-*` critics already carry against a rendered plan document. A
second, independent `_warn_on_failed_personas` call (labeled
`"Implement review"`, genuinely non-fatal this time) surfaces a failed
review-panel member or a failed tech-writer dispatch as a stderr WARNING —
exit code stays 0, and the state file still records the failed entry
verbatim — mirroring the same non-fatal-failure-visibility convention
Research and Plan already established.

**Script gap.** `_dispatch_implement_wave` dispatches a single synthetic
slice representing "the whole task," not real per-plan-step decomposition —
Phase 2's persisted shape (`orchestrator-plan.json`) has no
machine-parseable ordered list of implementation steps to derive
`IMPLEMENT_WAVE_SLICES` from. The script also does not implement the
three-stage inline review loop in `${CLAUDE_PLUGIN_ROOT}/knowledge/three-phase-workflow.md#phase-3-implement`
(`spec-reviewer` →
`quality-reviewer` → browser verification), nor the final `/code-review`
`fail`/`warn`/`pass` branching before its doc-review pass — the review
panel's `review_status` verdicts are persisted but not read or gated on;
a `fail` verdict has the same observable outcome (exit 0, state persisted)
as a clean pass. All of the above (the inline review loop, the
`/code-review` branching, real per-step decomposition, and verdict gating)
remain the operator's own responsibility today; tracked against spec
#1707/a future slice. Separately: `--resume` after a wave failure
re-dispatches `software-engineer` against a working tree that may already
carry partial edits from the failed attempt (a realistic case under
`PERSONA_DISPATCH_TIMEOUT_S`'s unverified 60s placeholder — see follow-up
#1716) — reconciling that state is the operator's own responsibility today,
not something this script checks or compensates for. This phase's dispatch
of `CODE_REVIEW_PANEL` is also the first place in this script where a
`/code-review`-shaped fan-out is driven deterministically rather than by
skill instructions. This is a deliberate, spec-#1707-scoped choice, not an
oversight against [ADR 0013](../../../docs/adr/0013-llm-driven-orchestration-over-deterministic-workflow-scripts.md#amendment-2026-08-02-orchestratorpys-deterministic-code_review_panel-dispatch)'s
LLM-driven-orchestration preference — see that ADR's amendment for why this
standalone script's fixed, judgment-free panel dispatch does not replace or
contradict the interactive `/code-review` skill's own unchanged fan-out.
