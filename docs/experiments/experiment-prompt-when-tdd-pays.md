# Experiment Prompt: When Does TDD Actually Pay Off?

**Type:** Reusable experiment prompt (hand this whole file to Claude to execute)
**Harness:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py) — **must be extended** (see "Extend the harness")
**Motivation:** [`FAQ.md` Q1](FAQ.md), [`tdd-vs-nontdd-report.md`](tdd-vs-nontdd-report.md),
[`3sizes-3arms-report.md`](3sizes-3arms-report.md)
**Prior run results:** [`when-tdd-pays-report.md`](when-tdd-pays-report.md)
**Supersedes:** `ambiguous-requirements-experiment.md` (Axis A) and
`experiment-prompt-design-discovery.md` (Axis B), merged here into one factorial.

The prior studies found **no advantage** for test-first — but they controlled away
the two conditions TDD's claimed benefits live in: **ambiguous requirements** (where
a failing test is meant to surface unstated decisions) and **open design with real
refactoring** (where incremental tests are meant to discover a better structure).
This experiment crosses both on one task suite and asks the unified question:
**under what conditions does TDD's claimed value actually appear — and is it largest
exactly where the prior experiment was blind?**

---

## What the first run found (2026-06-23, claude-sonnet-4-6)

The first execution of this experiment (288 cells, 4 tasks, 3 trials per cell) produced
four verdicts. They reframe the research questions for the next run:

| Finding | Implication for next run |
|---------|--------------------------|
| **H-A REJECTED (reversed):** test-after 67% EDGE vs tdd-refactor 33% under vague spec | The anchoring effect is real. Add `test-after-refactor` to test whether deferring test commitment AND refactoring combines both advantages |
| **H-B CONFIRMED:** tdd-refactor lowest blast radius (664 vs 700–770) | Refactoring matters for changeability. The new arm tests whether test-first is necessary to get it |
| **H-B2 CONFIRMED:** tdd-no-refactor (701) ≈ test-after (700) | **The refactor step is load-bearing, not test ordering.** But the experiment confounds refactoring with its test safety net — `test-after-refactor` isolates this |
| **H-C NOT CONFIRMED:** TDD's changeability gap is similar across clarity conditions | The advantage is structural (from refactoring), not spec-dependent |

**The critical confound the first run could not resolve:** tdd-refactor's changeability
advantage might come from (a) refactoring itself, (b) having tests before refactoring
that catch regressions, or (c) the iterative TDD cycle shaping the design incrementally.
The first run cannot distinguish these because all three are present simultaneously in
the tdd-refactor arm.

**The predicted best path — untested:** `test-after-refactor` (write code → write tests
against the working implementation → refactor with test safety net) is predicted to:

- Match test-after's EDGE advantage (67%) by deferring test commitment
- Match tdd-refactor's changeability (664 blast radius) by refactoring under test coverage
- Cost less than tdd-refactor ($0.44/stage) since there are no iterative red-green cycles
- Dominate every other arm across all three dimensions simultaneously

**This prediction is the primary question for the next run.**

**Token cost summary from first run (most to least expensive per stage):**

| arm | cost/stage | EDGE under vague | blast radius |
|-----|-----------|-----------------|--------------|
| tdd-refactor | $0.44 | 33% | **664** (best) |
| bduf | $0.24 | 0–67% | 770 |
| tdd-no-refactor | $0.22 | 0% | 701 |
| test-after | **$0.19** | **67%** (best) | 700 |
| test-after-refactor | *untested* | *predicted: ~67%* | *predicted: ~664* |

**Vague requirements finding (unchanged for next run):** The notifier task produced
EDGE=0% for every workflow — per-channel retry semantics were not inferrable from the
vague spec. This is a **spec-gap, not a workflow-gap**: no coding methodology recovers
information that was never stated. The correct response to a vague spec is a
clarifying conversation before any code is written. The next run should preserve a
task with an irreducible spec-gap to confirm this floor holds across workflows.

---

## Prompt

> Run one controlled experiment that crosses **requirement clarity** with
> **coding workflow** on a suite of **open-design** tasks, and grades each cell on
> two axes at once: **contract inference under ambiguity** and **changeability of
> the resulting design**. Reuse the isolation/cost primitives in
> `scripts/run_tdd_experiment.py`, but **extend it** to (a) select a clear or vague
> spec, (b) grade Stage 0 with a split CORE/EDGE acceptance, (c) apply a withheld
> **change chain**, and (d) record changeability, structural, and multi-rater
> review measurements per stage. Author open-design tasks with a deliberate
> design **trap** and both a clear and a vague spec over an **identical hidden
> contract**. Work on a feature branch; commit fixtures, the harness extension,
> raw data, and a report; do not open a PR unless asked.
>
> **Two factors:**
>
> - **Clarity** — `clear` (spec states architecture *and* edge-case decisions) vs
>   `vague` (omits both; the hidden acceptance is unchanged, so the *contract* is
>   fixed — only what the agent is *told* changes).
> - **Workflow** — `tdd-refactor` (strict RED-GREEN-**REFACTOR**, refactor
>   mandatory), `tdd-no-refactor` (test-first, never restructure), `test-after`
>   (code first, tests last), `test-after-refactor` (all production code first,
>   then tests against the working implementation, then refactor with the test
>   safety net in place — see "Arms"), `bduf` (design up front, then implement,
>   then tests), `ship` (run the `/specs`→`/plan`→`/build` pipeline: the `/specs`
>   phase authors acceptance criteria before any code is written; `/plan` produces
>   Gherkin scenarios per slice; `/build` executes RED-GREEN-REFACTOR with inline
>   review). **`ship` runs at `vague` only** — its value is in testing whether
>   structured spec synthesis resolves ambiguity better than test-first's
>   failing-test-as-specification; under a `clear` spec both arms trivially
>   converge and no comparison is possible.
>
> Grade every cell the same way: **CORE/EDGE** Stage-0 acceptance (ambiguity), a
> **withheld change chain** (changeability), deterministic **radon** structural
> metrics, and a blind **multi-rater** code+test review score. The unit of
> inference is the **task**; compare paired across tasks.

---

## Research questions & hypotheses (pre-register before looking at results)

- **RQ-A / ambiguity.** Does workflow change how well the agent infers *unstated*
  decisions? **H-A:** under `vague`, `tdd-refactor` passes more **EDGE** assertions
  than `test-after`; under `clear` there is no gap (a `workflow × clarity`
  interaction). **Null:** vagueness degrades all arms equally (test-first just
  locks in its own happy-path guess).
- **RQ-B / design.** Does workflow change the **changeability** of the design?
  **H-B:** `tdd-refactor` absorbs the change chain at lower cumulative cost /
  smaller blast radius than `test-after` and `bduf`. **H-B2 (mechanism):**
  `tdd-no-refactor` ≈ `test-after` < `tdd-refactor` ⇒ the benefit comes from
  **refactoring**, not test ordering.
- **RQ-C / the headline interaction.** Is TDD's advantage (on EDGE *and*
  changeability) **largest in the `vague + open-design` cell** — i.e. exactly where
  the prior null experiment could not look? This is the cell both claims predict
  TDD should win.
- **RQ-D / spec synthesis vs test-first.** Does `ship`'s explicit acceptance-criteria
  synthesis (the `/specs` phase authors the contract before any code is written)
  resolve ambiguity as well as or better than `tdd-refactor`'s failing-test-as-
  specification approach? **H-D:** under `vague`, `ship` EDGE pass rate ≥
  `tdd-refactor` because the `/specs` phase forces the agent to state every
  acceptance decision upfront, including those the vague spec omitted. **H-D2
  (mechanism):** `ship` changeability ≤ `tdd-refactor` because its inline review
  checkpoints in `/build` catch structural issues that `tdd-refactor`'s refactor
  step misses. **Null:** the `/specs` phase makes the same happy-path assumptions
  as any other arm — synthesising a spec from a vague prompt does not reliably
  surface EDGE decisions.
- **RQ-E / test-after-refactor dominance.** Does deferring test commitment *and*
  adding a refactor phase dominate all existing arms simultaneously? **H-E:** under
  `vague`, `test-after-refactor` EDGE pass rate ≥ `test-after` (≈67%) — because
  deferred tests capture the actual emergent contract, including edge cases the
  working implementation surfaced — AND blast radius ≈ `tdd-refactor` (≈664) —
  because refactoring under test coverage provides the same structural safety net as
  TDD's refactor step. If both hold, `test-after-refactor` dominates every existing
  arm: better EDGE than `tdd-refactor`, better changeability than `test-after`, lower
  cost than `tdd-refactor` (no iterative red-green cycles during initial build).
  **Null:** refactoring with tests written post-implementation produces the same
  structure as no-refactor arms — the incremental TDD red-green cycle shapes design
  in ways a post-facto test-then-refactor pass cannot replicate.

---

## Design: clarity × workflow (fractional factorial, paired by task)

| | tdd-refactor | tdd-no-refactor | test-after | test-after-refactor | bduf | ship |
|---|---|---|---|---|---|---|
| **clear** | ✓ anchor | – | ✓ anchor | ✓ anchor | – | – |
| **vague** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Run **all 6 arms at `vague`** (the novel regime where both benefits should appear)
and only the **3 anchor arms** at `clear` (to establish the interaction baseline) —
**9 arm-clarity cells per task** instead of 12. `test-after-refactor × clear` is
added as an anchor to give RQ-E a clean baseline: under a clear spec with no design
trap, how much does the refactor step help relative to `test-after` (the same code
written without a subsequent refactor)? `bduf × vague` is deliberately kept: it
tests whether committing to a *design* before requirements are clear helps or hurts.
`ship × vague` tests whether committing to an *explicit acceptance contract* (via
`/specs`) helps or hurts — a different mechanism from bduf. `ship` requires a
plugin-enabled `$HOME` per cell (same setup as the `build-pipeline` arm in the
prior 3-arm study). Model **fixed** (e.g. `claude-sonnet-4-6`), reported.

---

## Shared substrate: open-design tasks (clear + vague over one hidden contract)

Author **4–6** tasks. Each needs a **genuinely open design space** (≥2 viable
architectures) **and** a **trap** (a naive happy-path build passes Stage 0 but is
punished by a later change). For each task:

- `golden-repo.tar.gz` — a stub package (public API surface only).
- `spec_clear.md` — states behavior, the public surface, the intended module
  shape, **and** the edge-case decisions (empty input, ties, errors, ordering,
  rounding). ≥8 acceptance scenarios.
- `spec_vague.md` — same goal + public surface, but **omits both** the architecture
  guidance and every edge-case decision the EDGE acceptance checks. Genuinely
  buildable, not contradictory — the ambiguity is *unstated decisions*, not broken
  requirements.
- **Hidden acceptance (identical across clarity):**
  - `acc_core.py` — behavior stated even in the vague spec (happy path).
  - `acc_edge.py` — the omitted/ambiguous decisions. `acc_core ∪ acc_edge` = the
    full Stage-0 contract.
  - `acc_change1.py … acc_changeK.py` (K = 3–5) — each chain stage's contract,
    **including regression assertions** for all prior stages.
- `change1.md … changeK.md` — the withheld change chain, each modifying behavior on
  a *different* axis the spec didn't foreshadow; design ≥1 change to **punish the
  naive design** and reward a decoupled one.
- **Validate against TWO reference solutions — a naive one and a clean one:** both
  pass `acc_core`; the clean one also passes `acc_edge` and absorbs the whole chain
  cheaply; the **naive one is forced into a large rewrite by the trap change**. This
  proves the design signal exists. Never grade with a broken/impossible chain.
- `evals/experiments/exp-tdd-pays-<name>.json` with an `experiment` block listing
  the clarity variants and the chain (`specClear`, `specVague`,
  `coreGrade`/`edgeGrade`, `changeChain`, `gradeChain`).

Suggested tasks: `notifier` (multi-channel dispatch), `pricing` (stacking discount
rules), `report-render` (pluggable formats), `event-store` (append + projections),
`command-registry` (plugin dispatch), `workflow` (state machine + guards).

---

## Grading pipeline (one pass, three instruments)

Each cell runs **Stage 0 build → change chain 1..K**, with acceptance hidden during
every build and injected only at grading:

| Instrument | Measures | Answers |
|---|---|---|
| Stage-0 **CORE** vs **EDGE** pass | contract inference | RQ-A (under `clear`, EDGE≈100% for all arms — the baseline that makes EDGE-under-`vague` interpretable) |
| Withheld **change chain**: dispatch cost + turns, **blast radius** (files/functions touched, public-API churn, whether the prior suite caught the regression before the fix) | changeability | RQ-B / RQ-B2 |
| **radon** `cc`/`mi` over production modules at every stage | structural trajectory | RQ-B (does complexity grow faster as changes pile up?) |
| **Multi-rater** review: `structure`,`complexity`,`naming`,`performance` on prod + `test-review` on tests, **K=3 passes averaged (mean ± stddev)** | code/test quality | shared "final review" (beats reviewer variance) |
| **Interpretation variance** across trials (distinct EDGE behaviors observed) | convergence | RQ-A secondary (does `tdd-refactor` converge more?) |

---

## Fixed procedure (follow exactly)

### 0. Preconditions

`pip install coverage pytest radon`. The four instruction arms (`tdd-refactor`,
`tdd-no-refactor`, `test-after`, `bduf`) need no plugin. The `ship` arm requires a
**plugin-enabled `$HOME` template** — build it once with `cp -r ~/.claude/plugins
$TPL/.claude/` and pass `--build-home-template $TPL` to the harness (same pattern
as the `build-pipeline` arm in the prior 3-arm study; cost reads from the JSON
result, not the plugin meter). Confirm the model id and that nested `claude -p`
works (`IS_SANDBOX=1` is set by the harness).

### 1. Model

One fixed, capable model for the whole run, reported. The cost/quality winner flips
with model — hold it constant.

### 2. Arms (add to `ARM_PROMPTS`; keep `PYTEST_RULE`)

- **tdd-refactor:** strict TDD; after EACH test passes, REFACTOR toward the
  cleanest module boundaries/naming/duplication, re-run tests (stay green), *then*
  write the next test. Do not defer refactoring.
- **tdd-no-refactor:** test-first, but write only the MINIMUM to pass each test and
  DO NOT restructure — straight to the next test.
- **test-after:** all production code first, tests last.
- **test-after-refactor:** all production code first (same as `test-after`), *then*
  write tests against the working implementation — capturing the actual contract
  including edge behaviours the implementation surfaced — *then* refactor with the
  test safety net in place. **Do not write tests before seeing a working
  implementation; do not refactor before tests are green.** This arm tests the
  hypothesis that deferred test commitment and a test-protected refactor combine
  additively: `test-after`'s EDGE advantage (tests capture what the code actually
  does, not what a red-phase guess assumed) plus `tdd-refactor`'s changeability
  advantage (structural refactoring under test coverage), at lower cost than
  `tdd-refactor` (no iterative red-green cycles during initial build).
- **bduf:** first write a short `DESIGN.md` (modules + public interfaces), then
  implement the spec to that design, then write the tests. Note: `bduf` commits to
  an *architecture* upfront; it does not author acceptance criteria. This isolates
  the "design commitment" mechanism from the "acceptance synthesis" mechanism tested
  by `ship`.
- **ship** *(vague only; plugin arm):* invoke the `/specs`→`/plan`→`/build` pipeline
  headlessly (self-approve at each human gate so it does not stall). `/specs` authors
  explicit acceptance criteria from the vague spec before any code is written;
  `/plan` decomposes the feature into Gherkin-backed slices; `/build` executes
  RED-GREEN-REFACTOR with three-stage inline review checkpoints. The key difference
  from all instruction arms: the agent must *synthesise* the acceptance contract
  (including the edge-case decisions the vague spec omitted) as an explicit artifact
  before implementation begins.

The spec the arm reads is `spec_clear.md` or `spec_vague.md` per the cell.

### 3. Author the open-design tasks (the craft step — do this first)

Per "Shared substrate". Calibrate **two** things by piloting one task:

- **Trap:** naive ref passes Stage 0 but is rewritten by the trap change; clean ref
  absorbs it. If both absorb equally → no design signal, re-author.
- **Vagueness:** under `vague`, `acc_core` is ~always passable and `acc_edge` is
  *sometimes* missed. If EDGE is always passed, the vague spec leaked the answer; if
  never, it's unbuildable.

### 4. Extend the harness

Extend `run_tdd_experiment.py` (or a sibling) to, per cell:

1. Select `spec_clear.md`/`spec_vague.md`.
2. Stage 0 build → grade `acc_core.py` and `acc_edge.py` **separately**.
3. Change-chain stages 1..K, each seeded from the previous stage's *files* (fresh
   dispatch, files only), prompt "apply {changeN}; keep existing tests green",
   graded by `acc_changeN.py`.
4. Per stage record: correctness; changeability (cost/turns + blast radius from
   `git diff` between stages + public-API churn + prior-suite regression catch);
   radon `cc`/`mi`; and the **K=3 averaged** review-panel score (mean ± stddev).
Keep acceptance hidden during each build.

### 5. Execute (sharded — instruction arms are cheap)

`N = 3–5` trials per cell. Shard by task; cells are isolated, so run many runners
concurrently. Bound every test/coverage/mutant run with a wall-clock timeout
(already landed). Monitor non-destructively (row counts / `pgrep`); never kill the
session's own `claude`.

### 6. Analyze (per task, then paired across tasks)

- **RQ-A primary — EDGE pass:** `tdd-refactor − test-after` under `vague`, paired
  across tasks (sign + Wilcoxon); read the `workflow × clarity` interaction against
  the `clear` anchors.
- **RQ-B primary — changeability:** cumulative cost + cumulative blast radius to
  absorb the whole chain, per task per arm; paired arm differences. **RQ-B2:** the
  `tdd-no-refactor` vs `test-after` vs `tdd-refactor` isolation.
- **RQ-C — the headline:** quantify whether each arm's EDGE *and* changeability
  advantage is **largest in `vague + open-design`**.
- **RQ-D — spec synthesis:** `ship − tdd-refactor` on EDGE pass rate and cumulative
  changeability under `vague`, paired across tasks. Also compare `ship` to `bduf` on
  EDGE pass rate — this isolates acceptance-criteria synthesis from architecture
  commitment as mechanisms for resolving ambiguity. Report `ship`'s cost premium over
  the cheapest vague arm to frame the "does spec synthesis pay?" trade-off.
- **RQ-E — test-after-refactor dominance:** Three-way test against H-E. (a) EDGE
  under `vague`: `test-after-refactor` ≥ `test-after`? If yes, deferred tests
  survive a refactor phase without losing their EDGE advantage. If no, the refactor
  changes what the code does, so tests written before refactoring no longer match
  the final contract. (b) Blast radius: `test-after-refactor` ≈ `tdd-refactor`?
  If yes, test-protected refactoring produces equivalent structural benefit
  regardless of when the tests were written. If no, the iterative TDD cycle
  produces a design that a post-implementation refactor cannot replicate. (c) Cost:
  `test-after-refactor` < `tdd-refactor`? This should hold by construction (no
  red-green iteration during build). All three must confirm to declare H-E supported.
  A partial confirm is informative: it identifies which component of `tdd-refactor`'s
  advantage (EDGE, changeability, or both) requires early test commitment.
- **Secondaries:** radon trajectory; multi-rater code/test/design score (mean ±
  stddev — treat differences smaller than the stddev as noise); interpretation
  variance; regression-catch rate.

### 7. Report

Write `docs/experiments/when-tdd-pays-report.md`: the clarity × workflow grid, the
RQ-A / RQ-B / RQ-C verdicts and the RQ-B2 mechanism isolation, the RQ-D
`ship`-vs-`tdd-refactor` spec-synthesis verdict, the RQ-E `test-after-refactor`
dominance verdict (all three conditions: EDGE ≥ `test-after`, blast radius ≈
`tdd-refactor`, cost < `tdd-refactor`), honest limitations (n, single model,
autonomous-only, reviewer variance, trap+vagueness calibration), reproducibility
commands, and a recommendation. Commit the report **and** raw data under
`docs/experiments/data/`.

---

## Best path forward (based on first-run evidence, pending RQ-E confirmation)

The first run and the predicted outcome of the second run point to the same
practical workflow hierarchy. Apply this pending RQ-E confirmation:

**If requirements are clear and the design is settled:**
`test-after` — cheapest arm ($0.19/stage), EDGE comparable to all arms under clear
spec (design is low-risk), blast radius acceptable (700). There is no need for
the refactor step when the design space is constrained.

**If requirements are vague or the design is open:**
`test-after-refactor` (predicted) — write all production code first so you see the
full shape of the problem before committing to a test contract, then write tests
against the working implementation to lock in the actual contract including emergent
edge behaviours, then refactor with the test safety net. Expected outcome: EDGE
≈67% (matching `test-after`), blast radius ≈664 (matching `tdd-refactor`), cost
≈$0.25–0.30/stage (between `test-after` and `tdd-refactor`).

**If requirements are irreducibly vague (spec-gap, not ambiguity):**
Stop before any code. The notifier finding from the first run is definitive: when a
vague spec omits semantics that cannot be inferred from context (e.g. per-channel
retry behaviour), no coding workflow recovers the missing information. EDGE=0% for
every arm regardless of workflow. The correct response is a clarifying conversation
before any implementation starts. The workflow choice is irrelevant until the spec
is complete enough to make edge decisions discoverable.

**Decision table (predicted, pending RQ-E):**

| Condition | Recommended arm | Why |
|-----------|----------------|-----|
| Clear spec, settled design | `test-after` | Cheapest; EDGE gap closes under clear spec |
| Vague spec OR open design | `test-after-refactor` | Combines deferred commitment (EDGE) + test-safe refactor (changeability) at moderate cost |
| Need explicit acceptance artefact | `ship` | `/specs` phase forces upfront contract synthesis; test if it resolves vagueness better than failing tests |
| Spec has irreducible gaps | Clarify first | No workflow recovers unstated semantics |

**What would falsify this:** RQ-E's null result. If `test-after-refactor` blast
radius is significantly worse than `tdd-refactor` (≥10% higher on average), then
the iterative TDD cycle shapes the design in ways a post-facto refactor cannot
replicate, and `tdd-refactor` remains the correct choice for open-design tasks
despite its higher cost. If `test-after-refactor` EDGE falls below `test-after`
(i.e. the refactor phase changes the implementation enough that post-refactor tests
diverge from pre-refactor ones), then the arm provides no EDGE advantage over
plain `test-after` and is simply `tdd-refactor` written in a different order.

---

## Guardrails (lessons already paid for — do not relearn)

1. **Hide acceptance during every build** (Stage 0 and each chain stage), or all
   arms just make the given tests pass and both signals die.
2. **Verify the refactor arm actually refactors.** `tdd-refactor` must show
   non-trivial structural churn *between* green and stage-end (diff intermediate vs
   final). If it doesn't, you're re-running the prior null — the whole point is that
   the earlier test-first arm stopped at GREEN.
3. **Calibrate the trap AND the vagueness** (per step 3): naive-punished/clean-absorbs,
   and core-always/edge-sometimes. An un-calibrated task answers nothing.
4. **Beat reviewer variance.** Average **K ≥ 3** review passes and report stddev;
   lean on the **deterministic radon metrics** and **objective blast-radius/EDGE**
   numbers as primary evidence, not the LLM review score (the prior run saw a naming
   agent score 0/19/4 on near-identical code).
5. **Cost/turns come from the JSON result**, not the plugin meter (it doesn't fire
   in nested dispatch). The harness reads `--output-format json`.
6. **Hold the model fixed and report it.**
7. **Pre-register** N, both primaries (EDGE under vague; cumulative changeability),
   the RQ-C interaction, and the RQ-D `ship`-vs-`tdd-refactor` comparison before
   running; the task is the unit of inference; no data-dependent stopping.
8. **Parallelize but isolate** — each cell gets its own worktree + `$HOME`. The
   `ship` arm additionally needs its own plugin-enabled `$HOME` template (see step
   0); do not share `$HOME` between `ship` cells and instruction cells.

## Out of scope (by decision)

- **Human / designer-in-the-loop** and the **clarification-oracle** arm. Every arm
  runs fully autonomously; the experiment measures what the workflow alone produces.

## Expected deliverables

- `evals/experiments/exp-tdd-pays-<task>.json` + open-design fixtures (stub,
  `spec_clear.md`, `spec_vague.md`, hidden `acc_core.py`/`acc_edge.py`,
  `change1..K.md`, `acc_change1..K.py`), each **validated against a naive and a
  clean reference**.
- The harness extension (clarity selection + CORE/EDGE grading + change-chain stages
  - blast-radius/radon/multi-rater instrumentation + `ship` plugin-home support).
- Raw data JSONL under `docs/experiments/data/`.
- One report with the clarity × workflow grid and the RQ-A / RQ-B / RQ-B2 / RQ-C /
  RQ-D / RQ-E verdicts and recommendation.
