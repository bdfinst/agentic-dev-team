# Implementation Checklist — External-Review Improvements (#98)

Local, sequenced working checklist for the 17 children of [#98](https://github.com/bdfinst/agentic-dev-team/issues/98).
Source report: [`docs/proposed-improvements-from-external-reviews.md`](../docs/proposed-improvements-from-external-reviews.md).

Ordering principle: **cheap self-tests first → observability spine → measurement-dependent bets → paradigm work.**
Each wave is gated on the prior wave's infrastructure, not just preference.

> **Re-prioritized under the North Star (2026-06-07).** The wave ordering below predates the
> North Star (`plugins/dev-team/CLAUDE.md`: *reduce friction, not reputation*). For the current
> KEEP / MODIFY / REJECT verdict on each item — which strips reputational/novelty justification out
> of the "Impact" rating — see [`docs/north-star-task-reevaluation.md`](../docs/north-star-task-reevaluation.md).
> The feedback loop those items feed **already exists** as `/session-review` (#127/#131); the only
> remaining loop work is the deltas in
> [`docs/specs/session-review-enhancements.md`](../docs/specs/session-review-enhancements.md).
> Headlines: #113 closes as shipped; #139 demotes (rework already extracted) and #106 narrows; #114
> rejected; #108/#112 deferred to ADR scope; #110/#111 narrowed; #140 (+#102) and #99 are the teeth to finish.

---

## Wave 0 — Cheap, high-leverage, unblock everything else

These pay for themselves immediately and create the harness the later waves reuse.

- [x] **#99 — Agent-eval regression gate in CI** *(High / Low)*
  - No dependencies. Builds the reusable eval-in-CI runner that #101, #103, #108, #110 lean on.
  - Start here: even a 1-trial smoke run closes the biggest gap both reviews named.
  - Done: `scripts/eval_grade.py` (deterministic, model-free grader + corpus check), `evals/baseline.json` + `evals/README.md`, `.github/workflows/agent-eval.yml` (model-free structural gate always; live regression gate when `ANTHROPIC_API_KEY` present, else skipped-not-failed), grader unit tests in `tests/repo/eval_grader_tests.bats`.
- [x] **#100 — Prose/Targets slop cleanup + de-buzzword CLAUDE.md** *(Med / Low)*
  - No dependencies. Pure editing; do alongside #99.
  - Establishes the "every quantitative claim names its instrument" rule that #102/#106 later satisfy.
  - Done: removed "federated learning" + "LSTM-inspired gates" metaphors and the un-instrumented Targets numbers from `plugins/dev-team/CLAUDE.md`; added a "Claims discipline" rule; `tests/docs/prose_honesty_test.bats` is the deterministic sensor that keeps the prose clean. Post-merge audit (#137) extended the sensor to **all** shipped prose and cleaned the same targets in the `performance-metrics` / `governance-compliance` skill docs.
  - Follow-up (open): **#141** — the local `pre-push` `eslint` is red on malformed-by-design fixture dirs (`knowledge/rule-fixtures/**`, `tests/fixtures/**/commitlint.config.js`), so the gate is habitually bypassed; add eslint ignores so the local gate is green and meaningful. (Surfaced by #137, out of #100's original scope.)
- [x] **#104 — `updatedInput` hook-contract conformance test** *(Med / Low)*
  - No dependencies. Isolated bats/integration test protecting model routing.
  - Done: `tests/hooks/updated_input_contract_tests.bats` pins the exact PreToolUse rewrite envelope (incl. 3-hop chain + deny shape), and the model-routing hook tests now run in CI (`plugin-tests.yml`) — previously `tests/hooks/` was excluded.
- [x] **#101 — Eval-corpus-as-semver contract** *(High / Low–Med)*
  - Depends on: #99 (reuses the eval runner + baseline).
  - Wire the patch/minor/major classifier into release-please once the runner exists.
  - Done: `scripts/eval_semver_classify.sh` classifies expected-corpus diffs (none→patch / additive→minor / editing→major) and asserts the conventional-commit type matches; wired as a PR job in `agent-eval.yml`; tests in `tests/repo/eval_semver_classify_tests.bats`.

**Wave 0 exit:** agents are tested on every PR; routing has a sensor; CLAUDE.md claims are honest; prompt semver is defined.

---

## Wave 1 — Observability spine

Nothing downstream can be evidence-based without these two. Build them before the measurement bets.

- [x] **#102 — Runtime cost/token metering** *(High / Med)*
  - No hard dependency, but do after #100 (it provides the instrument #100 promised for cost claims).
  - Required by #111 (process eval needs a real cost meter to compare pipelines).
  - Done (core): `hooks/lib/cost_meter.py` parses the session transcript (token usage isn't in hook payloads), attributes tokens/$ per agent+model via `knowledge/model-pricing.json`, recorded by the `Stop`/`SubagentStop` hook to `metrics/cost-metering.jsonl`; `/cost-report` skill prints spend + rolling-baseline regression. Tests in `tests/repo/cost_meter_tests.bats`.
  - Follow-ups (open): **#139** — add per-fix-loop-iteration & per-phase granularity (landed meter buckets by agent/model/session only); **#140** — wire the existing `regression` subcommand into CI (it runs in no workflow today, so cost regressions can merge unnoticed); **#142** — account-level pace/quota guidance (optional tail of the seed).
- [x] **#106 — Opt-in privacy-clean telemetry beacon** *(High / Med)*
  - No hard dependency. Reuses the append-only event-log convention.
  - Required by #112 (exposure-based gating) and pairs with #113 (auto-learning signals).
  - Done: `hooks/telemetry.sh` (default-off, local-only) captures command/skill usage (`UserPromptSubmit`) and pre-commit gate fired/bypassed (`PreToolUse` Bash) as minimal events (name + outcome + version, no payloads) to `metrics/telemetry.jsonl`; `/telemetry` skill manages consent and reports usage + bypass rate. Tests in `tests/repo/telemetry_tests.bats`.

**Wave 1 exit:** per-dispatch cost is measurable; gate-bypass/usage telemetry exists (opt-in).

---

## Wave 2 — Measurement-dependent & novel bets

Now that the eval runner (Wave 0) and meters (Wave 1) exist, these become tractable and falsifiable.

- [ ] **#103 — Eval variance & saturation data collection** *(Med / Med)*
  - Depends on: #99 (eval runner). Feeds back into #99's thresholds (which fixtures to quarantine).
- [ ] **#107 — Knowledge ablation testing (demand-side)** *(Med / Med)*
  - Depends on: #99 (eval harness). Ablate a knowledge file → diff grades.
- [ ] **#108 — Mutation testing for prose/prompts** *(High / Med–High)*
  - Depends on: #99 (per-agent eval reruns). Pilot on one agent first.
  - Makes #100's "prose with no sensor rots" law mechanically detectable.
- [ ] **#110 — Persona-vs-context-boundary empirical test** *(High / Med)*
  - Depends on: #99 + #103 (need variance to trust the persona-on/off delta).
- [ ] **#111 — Process/workflow eval (A/B the ceremony)** *(High / High)*
  - Depends on: #102 (cost meter) and the eval harness. The hard part is unbiased ground-truth tasks.

**Wave 2 exit:** agent stability, knowledge value, prose coverage, persona value, and workflow value are all quantified.

---

## Wave 3 — Paradigm & long-tail

Sequence after the evidence (Wave 2) and telemetry (Wave 1) exist so these are informed, not speculative.

- [ ] **#112 — Per-increment trunk integration topology (ADR/spike)** *(Paradigm / High)*
  - Depends on: #111 (evidence the ceremony is/ isn't worth it) + #106 (exposure telemetry).
  - Write as ADR/spike first — the deepest reframe; don't implement blind.
- [ ] **#109 — Concurrency / multiplayer collision model** *(High / Med–High)*
  - Independent. Phase 1 (reproduce collisions) is a cheap afternoon; schedule when team/N=2 matters.
- [ ] **#113 — Automatic post-session learning loop** *(Med / Med–High)*
  - Pairs with #106 (telemetry signals feed candidate learnings). Must preserve audited-write governance.
- [ ] **#105 — Resolve Multi-LLM/Gemini vestigiality** *(Med / Low–High)*
  - Independent. Default to deletion (Low) unless a real agent-agnostic roadmap is committed (then High + ADR).
- [ ] **#114 — Component extraction / publication plan** *(Med / Low)*
  - Independent. Best done after #108/#116-style work makes the components' novelty concrete.
- [ ] **#115 — Reconcile `agent-ast.md` orphan spec** *(Low / Low)*
  - Independent hygiene. Do anytime; quick win.

**Wave 3 exit:** trust-topology decided; multiplayer characterized; learning automated; scope honest; best ideas distributed; no orphan specs.

---

## Patch issues — residual scope from partially-landed work

The Wave 0/1 PRs (#122, #126, #137) shipped the **core** of their parent issues but left
measurable residual scope. Rather than reopen closed issues, the remainder is tracked as
focused patch issues:

- [ ] **#139 — Cost meter: per-fix-loop-iteration & per-phase granularity** *(refines #102)*
  - Landed meter is per-agent/model/session; #111 (process eval) needs finer attribution to compare pipelines fairly.
- [ ] **#140 — Wire cost-regression check into CI** *(refines #102)*
  - `cost_meter.py regression` exists but runs in no workflow; #102's "CI/regression hook" acceptance is only half-met.
- [ ] **#141 — eslint-ignore malformed fixture dirs** *(refines #100, surfaced by #137)*
  - Un-breaks the local `pre-push` gate so it stops being routinely `--no-verify`'d.
- [ ] **#142 — Account-level cost pace/quota guidance** *(refines #102, optional)*
  - The explicitly-optional tail of #102's seed; file kept low-priority.

> Note: **#106** remains open on GitHub despite its core landing in #126 — track any remaining
> telemetry scope on the issue itself rather than as a separate patch.

---

## Dependency summary

```
#99 ─┬─> #101
     ├─> #103 ─┐
     ├─> #107  ├─> #110
     └─> #108  │
#102 ──> #111 ─┴─> #112 <── #106
#106 ──> #113
(independent: #100, #104, #105, #109, #114, #115)
```

## Suggested PR cadence

- Each child is its own PR with a `feat:`/`ci:`/`docs:`/`test:` conventional-commit type.
- Run `/specs` per child using the spec-prompt seed in its GitHub issue.
- Keep waves as loose milestones; within a wave, items can parallelize.
