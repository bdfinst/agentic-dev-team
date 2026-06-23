# Experiment Prompt: When Does TDD Actually Pay Off?

**Type:** Reusable experiment prompt (hand this whole file to Claude to execute)
**Harness:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py) — **must be extended** (see "Extend the harness")
**Motivation:** [`FAQ.md` Q1](FAQ.md), [`tdd-vs-nontdd-report.md`](tdd-vs-nontdd-report.md),
[`3sizes-3arms-report.md`](3sizes-3arms-report.md)
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
> - **Clarity** — `clear` (spec states architecture *and* edge-case decisions) vs
>   `vague` (omits both; the hidden acceptance is unchanged, so the *contract* is
>   fixed — only what the agent is *told* changes).
> - **Workflow** — `tdd-refactor` (strict RED-GREEN-**REFACTOR**, refactor
>   mandatory), `tdd-no-refactor` (test-first, never restructure), `test-after`
>   (code first, tests last), `bduf` (design up front, then implement, then tests).
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

---

## Design: clarity × workflow (fractional factorial, paired by task)

| | tdd-refactor | tdd-no-refactor | test-after | bduf |
|---|---|---|---|---|
| **clear** | ✓ anchor | – | ✓ anchor | – |
| **vague** | ✓ | ✓ | ✓ | ✓ |

Run **all 4 arms at `vague`** (the novel regime where both benefits should appear)
and only the **2 anchor arms** at `clear` (to establish the interaction baseline) —
**6 arm-clarity cells per task** instead of 8. `bduf × vague` is deliberately kept:
it tests whether committing to a design *before* requirements are clear helps or
hurts. Model **fixed** (e.g. `claude-sonnet-4-6`), reported.

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
`pip install coverage pytest radon`. All arms are **instruction-level** (no plugin)
— no plugin HOME template needed. Confirm the model id and that nested `claude -p`
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
- **bduf:** first write a short `DESIGN.md` (modules + public interfaces), then
  implement the spec to that design, then write the tests.

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
- **Secondaries:** radon trajectory; multi-rater code/test/design score (mean ±
  stddev — treat differences smaller than the stddev as noise); interpretation
  variance; regression-catch rate.

### 7. Report
Write `docs/experiments/when-tdd-pays-report.md`: the clarity × workflow grid, the
RQ-A / RQ-B / RQ-C verdicts and the RQ-B2 mechanism isolation, honest limitations
(n, single model, autonomous-only, reviewer variance, trap+vagueness calibration),
reproducibility commands, and a recommendation. Commit the report **and** raw data
under `docs/experiments/data/`.

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
   and the RQ-C interaction before running; the task is the unit of inference; no
   data-dependent stopping.
8. **Parallelize but isolate** — each cell gets its own worktree + `$HOME`.

## Out of scope (by decision)
- **Human / designer-in-the-loop** and the **clarification-oracle** arm. Every arm
  runs fully autonomously; the experiment measures what the workflow alone produces.

## Expected deliverables
- `evals/experiments/exp-tdd-pays-<task>.json` + open-design fixtures (stub,
  `spec_clear.md`, `spec_vague.md`, hidden `acc_core.py`/`acc_edge.py`,
  `change1..K.md`, `acc_change1..K.py`), each **validated against a naive and a
  clean reference**.
- The harness extension (clarity selection + CORE/EDGE grading + change-chain stages
  + blast-radius/radon/multi-rater instrumentation).
- Raw data JSONL under `docs/experiments/data/`.
- One report with the clarity × workflow grid and the RQ-A / RQ-B / RQ-B2 / RQ-C
  verdicts and recommendation.
