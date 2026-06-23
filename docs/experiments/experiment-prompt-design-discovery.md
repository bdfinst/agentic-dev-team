# Experiment Prompt: Does Test-First *Discover a Better Design*?

**Type:** Reusable experiment prompt (hand this whole file to Claude to execute)
**Harness:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py) — **must be extended** (see "Extend the harness")
**Motivation:** [`FAQ.md` Q1](FAQ.md), [`tdd-vs-nontdd-report.md`](tdd-vs-nontdd-report.md),
[`3sizes-3arms-report.md`](3sizes-3arms-report.md)

The prior studies found **no design advantage** for test-first — but they measured
design by static review findings on katas with a largely *determined* shape, and
the test-first arm **stopped at GREEN** (never refactored), so they tested "TDD
minus its design step." This experiment is built to actually test the design
claim: *"by writing tests one after the other, you gradually discover the design
you feel is optimal."* **Out of scope (by decision): the human/designer-in-the-loop
condition** — every arm runs fully autonomously.

---

## Prompt

> Run a controlled experiment testing whether **incremental test-first with
> refactoring discovers a better — i.e. more changeable and better-structured —
> design** than writing tests after, or designing big up front. Reuse the
> isolation/cost primitives in `scripts/run_tdd_experiment.py`, but **extend it**
> to (a) apply a withheld **change chain** (not a single change) and (b) record
> **changeability, structural, and design-review** measurements per stage. Author
> **open-design** tasks where more than one architecture is viable and a naive
> build is later punished. Work on a feature branch; commit fixtures, the harness
> extension, raw data, and a report; do not open a PR unless asked.
>
> **Arms (the only variable is *how/when* design happens):**
> 1. **tdd-refactor** — strict RED → GREEN → **REFACTOR**, and the refactor is
>    *mandatory*: after each test goes green, restructure toward the cleanest
>    design before writing the next test.
> 2. **tdd-no-refactor** — strict test-first, but **never** restructure: write the
>    minimum to pass each test and move on. (Isolates test-ordering from refactoring.)
> 3. **test-after** — all production code first, tests authored at the end.
> 4. **bduf** — **big design up front**: first write a short design (modules +
>    public interfaces), then implement, then tests. The foil the claim argues against.
>
> Grade every arm the same way: hidden acceptance for correctness, a **withheld
> change chain** for changeability, deterministic structural metrics, and a blind
> **multi-rater** design-review score. The unit of inference is the **task**;
> compare arms **paired across tasks**.

---

## Hypotheses (pre-register before looking at results)

- **H1 (design payoff):** `tdd-refactor` absorbs the change chain at **lower
  cumulative cost / smaller blast radius** than `test-after` and `bduf`.
- **H2 (mechanism isolation):** `tdd-no-refactor` ≈ `test-after` (and < `tdd-refactor`).
  If true, the design benefit comes from **refactoring**, not test ordering — the
  conclusion the prior run hinted at.
- **H0 (null):** no arm differs on changeability/structure beyond noise — for an
  autonomous agent, design does not "emerge" from any of these workflows.

---

## Fixed procedure (follow exactly)

### 0. Preconditions
- `pip install coverage pytest radon` (radon supplies deterministic cyclomatic
  complexity + maintainability index; the harness already needs coverage/pytest).
- All four arms are **instruction-level** (no plugin), so no plugin HOME template
  is needed. Confirm the model id and that nested `claude -p` works (`IS_SANDBOX=1`
  is set by the harness).

### 1. Model
One **fixed, capable** model for the whole run, reported (e.g. `claude-sonnet-4-6`).
The cost/quality winner flips with model — hold it constant.

### 2. Arms
Add four `ARM_PROMPTS` to the harness (keep the existing `PYTEST_RULE`):
- **tdd-refactor:** "Implement the spec in {spec} using strict TDD. After EACH
  test passes, REFACTOR: improve module boundaries, naming, and duplication so the
  code is the cleanest design you can see, then re-run tests (they must stay
  green) before writing the next test. Do not defer refactoring."
- **tdd-no-refactor:** "Implement the spec in {spec} test-first, but write only the
  MINIMUM code to make each test pass and DO NOT restructure or refactor — move
  straight to the next test."
- **test-after:** (reuse existing) all production code first, tests last.
- **bduf:** "First write a short design to `DESIGN.md`: the modules you will create
  and their public interfaces. Then implement the spec in {spec} to that design.
  Then write the tests."

### 3. Authoring open-design tasks (the craft step — do this first)
Author **4–6** tasks. Each needs a **genuinely open design space** (≥2 viable
architectures) and a **trap**: a naive happy-path build passes Stage 0 but is
*punished* by a later change. For each:
- `golden-repo.tar.gz` — a stub package (public API surface only).
- `spec.md` — the initial feature. State the *behavior* and public surface, but
  **do not prescribe internal architecture** (≥8 acceptance scenarios).
- `change1.md … changeK.md` — a **withheld change chain** (K = 3–5), revealed one
  at a time, each modifying behavior along a *different* axis the spec didn't
  foreshadow (new variant/backend, new output format, a cross-cutting rule, a
  bulk/perf requirement). Design at least one change to **punish the obvious naive
  design** and reward a decoupled one.
- `acc.py`, `acc_change1.py … acc_changeK.py` — **hidden** acceptance per stage;
  each later file **includes regression assertions** for all prior stages.
- **Validate against ≥2 reference solutions** (a naive one and a clean one):
  confirm both pass Stage 0, the clean one absorbs the chain cheaply, and the
  naive one is forced into a large rewrite by the trap change. Never grade with a
  broken or impossible chain.
- `evals/experiments/exp-dd-<name>.json` with an `experiment` block listing the
  chain (`changeChain: ["change1.md", …]`, `gradeChain: [["acc.py"], …]`).

Suggested open-design tasks: `notifier` (multi-channel dispatch), `pricing`
(stacking discount rules), `report-render` (pluggable output formats),
`event-store` (append + projections), `command-registry` (plugin dispatch),
`workflow` (state machine + guards).

### 4. Extend the harness (the new measurement)
Extend `run_tdd_experiment.py` (or a sibling runner) to, per cell:
1. **Stage 0 build** from the golden repo with the arm prompt.
2. **Change-chain stages 1..K:** each seeded from the *previous stage's files*
   (fresh dispatch, files only), prompt = "apply the change in {changeN}; keep the
   existing tests green." Grade each with its hidden acceptance (incl. regressions).
3. Record per stage:
   - **Correctness:** hidden-acceptance pass/fail.
   - **Changeability:** dispatch **cost + turns** to apply the change, and **blast
     radius** from `git diff` between stages — files touched, functions touched,
     and **public-API churn** (added/removed/renamed exported names). Also whether
     the *prior* test suite caught the regression before the agent fixed it.
   - **Structure:** run `radon cc -s` and `radon mi` over production modules
     (deterministic), recorded at every stage.
   - **Design-review score:** run the review panel (`structure`, `complexity`,
     `naming`, `performance`) **K=3 times** and average; record mean **and stddev**
     (beat reviewer variance — see Guardrails).
   Keep acceptance hidden during each build; inject only at grading.

### 5. Execute (sharded — instruction arms are cheap)
Run `N=3–5` trials per (task × arm). Shard by task; cells are isolated, so run
many runners concurrently. Bound every test/mutant/coverage run with a wall-clock
timeout (already landed). Monitor non-destructively (row counts / `pgrep`); never
kill the session's own `claude`.

### 6. Analyze (per task, then paired across tasks)
- **Primary — changeability:** cumulative cost + cumulative blast radius to absorb
  the *whole chain*, per task per arm (median over trials). Paired arm differences
  across tasks + sign/Wilcoxon. **H1:** tdd-refactor lowest.
- **Mechanism — H2 isolation:** the `tdd-no-refactor` vs `test-after` vs
  `tdd-refactor` contrast. Report whether refactoring (not test order) carries the
  effect.
- **Structure:** radon CC/MI trajectory across stages (does one arm's complexity
  grow faster as changes pile up?).
- **Design score:** review-panel mean ± stddev per arm; treat any arm difference
  smaller than the stddev as noise.
- **Correctness / regressions:** chain pass rate; how often each arm's own suite
  caught a chain regression before the fix.

### 7. Report
Write `docs/experiments/design-discovery-report.md`: the arm × {changeability,
structure, design-score} grid, the H1 and H2 verdicts, honest limitations (n,
single model, autonomous-only, reviewer variance, trap calibration), reproducibility
commands, and a recommendation. Commit the report **and** the raw data under
`docs/experiments/data/`.

---

## Guardrails (lessons already paid for — do not relearn)

1. **Hide acceptance during every build** (Stage 0 and each chain stage), or all
   arms just make the given tests pass and the design signal dies.
2. **Verify the refactor arm actually refactors.** `tdd-refactor` must show
   non-trivial structural churn *between* green and stage-end (diff the
   intermediate vs final); if it doesn't, you're re-running the prior null. This is
   the whole point — the prior test-first arm stopped at GREEN.
3. **Calibrate the trap.** Each task's naive reference must pass Stage 0 but be
   forced into a large rewrite by the trap change; the clean reference must absorb
   it cheaply. If both absorb it equally, the task has no design signal — re-author.
4. **Beat reviewer variance.** Review agents vary run-to-run (the prior run saw a
   naming agent score 0/19/4 on near-identical code). Average **K≥3** passes and
   report stddev; lean on the **deterministic radon metrics** and the **objective
   blast-radius** numbers as the primary design evidence, not the LLM review score.
5. **Cost/turns come from the JSON result**, not the plugin meter (it doesn't fire
   in nested dispatch). The harness reads `--output-format json`.
6. **Hold the model fixed and report it.**
7. **Pre-register** N, the changeability primary endpoint, and the H2 isolation
   contrast before running; the task is the unit of inference.
8. **Parallelize but isolate** — each cell gets its own worktree + `$HOME`.

## Expected deliverables
- `evals/experiments/exp-dd-<task>.json` + open-design fixtures (stub, `spec.md`,
  `change1..K.md`, hidden `acc*.py`), each validated against a naive **and** a clean
  reference solution.
- The harness extension (change-chain stages + blast-radius/radon/multi-rater
  instrumentation).
- Raw data JSONL under `docs/experiments/data/`.
- One report with the arm grid, the H1 (design payoff) and H2 (refactor-not-test-order)
  verdicts, and the recommendation.
