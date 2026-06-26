# Experiment Prompt: Which agentic workflow yields maintainable, well-tested code at minimum cost

**Type:** Reusable experiment prompt (hand this whole file to Claude to execute)
**Harness:** [`scripts/run_refactor_experiment.py`](../../scripts/run_refactor_experiment.py)
**Supersedes the design of:** [`06-experiment-prompt-refactor-granularity-revised.md`](06-experiment-prompt-refactor-granularity-revised.md)
(this re-scopes that experiment to the question below and drops everything that does not serve it)

**Status: specified, harness ready, NOT run at scale.** New arms validated under
`--skip-dispatch` and a 1-task cost pilot.

---

## The question

> To achieve code that is **maintainable, well structured, and tested with good tests at
> minimum cost**, which agentic workflow works best?

Everything in the experiment exists to answer that and nothing else.

## Two crossed factors (the variable matrix)

| factor | levels |
|---|---|
| **A. Test/code ordering** | test-first / test-after |
| **B. Batch size** | small (incremental, per-behavior) / big (all-at-once) |
| **C. Authorship** | 1 agent / 2 context-isolated agents |

The four named workflows are exactly the **A×B** cells:

| workflow | ordering × batch |
|---|---|
| **W1 — Classic TDD (Kent Beck)** | test-first × small |
| **W2 — Code first, tests second, small batches** | test-after × small |
| **W3 — All code, then all tests** | test-after × big |
| **W4 — All tests, then code to pass** | test-first × big |

Crossing the 4 workflows with the 2 authorship levels gives a **2×2×2** design. One cell —
**W1 × 2 agents** — is dropped: Beck's RED-GREEN-REFACTOR loop is a single integrated cycle,
and splitting it across two context-isolated agents is either heavy-handoff ping-pong or no
longer TDD. That leaves **7 cells**.

## Held constant (eliminated as variables)

These were factors in run 04 / prompt 06; the question above fixes them, so they are removed:

| held constant | fixed to | removes |
|---|---|---|
| Refactoring | **always**, after tests pass each iteration | the `none` / `one-shot`-only granularity arms as *separate* cadence conditions |
| Spec clarity | **clear** | the clear/vague crossing |

Refactoring being mandatory does **not** remove a refactor *step* — every arm refactors after
green. "Each iteration" means per-behavior for the small-batch workflows and once-after-green
for the big-batch workflows (which have a single iteration).

## The 7 cells and the arms that implement them

| cell | workflow × authorship | harness arm | status |
|---|---|---|---|
| C1 | W1 TDD × 1 agent | `tdd-refactor` | existing |
| C3 | W2 small × 1 agent | `continuous-single` | existing |
| C4 | W2 small × 2 agents | `continuous-split` | existing |
| C5 | W3 big × 1 agent | `one-shot-single` | existing |
| C6 | W3 big × 2 agents | `one-shot-split` | existing |
| **C7** | **W4 big × 1 agent** | **`all-tests-first-single`** | **new** |
| **C8** | **W4 big × 2 agents** | **`all-tests-first-split`** | **new** |

The existing `one-shot` arms already *are* W3: one agent (or coder+tester) writes everything,
then a separate, revertable refactor pass runs after green. Only **W4** — write the whole test
suite first, then production code to pass it — was missing. Two new arms add it:

- `all-tests-first-single`: one agent writes the full failing suite, then the production code to
  pass it, then a separate refactor pass.
- `all-tests-first-split`: an isolated tester writes the full failing suite, then an isolated
  coder writes production code to pass it, then a separate refactor pass.

Both use the `one-shot` refactor mechanism (separate dispatch, test edits reverted to the green
snapshot) so the **tests-frozen-during-refactor invariant** holds exactly as in every other arm.

The `no-refactor-*` arms are **not used** — refactoring is mandatory now.

## Outcome measures (what "best" means)

All already emitted by the harness; map 1:1 to the three goals plus cost:

| goal | measured by |
|---|---|
| **Maintainable / well structured** | radon MI + CC, lizard CCN / tokens, blast radius across the 3-change chain (changeability) |
| **Tested with good tests** | mutation score, branch coverage, CORE + EDGE acceptance pass, test smells (assertless tests, mock density, sleeps) |
| **Minimum cost** | `cost_usd`, tokens, turns (raw and per quality unit) |

Report every quality figure **raw and per-dollar**, and name the efficient frontier: which
workflow buys the most maintainability + test quality per dollar.

## Cost (firmed by a 1-task pilot)

Per-cell costs: run-04 actuals (cross-task mean) for the 5 existing arms; a 1-task `fare`
pilot for the 2 new arms, nudged +5% since `fare` runs ~5% below the cross-task mean.
The pilot arms ran clean — core+edge pass, mutation 1.0, all 3 changes pass, 0 invariant
violations.

| cell | arm | $/cell | basis |
|---|---|--:|---|
| C3 | `continuous-single` | 0.99 | run-04 actual |
| C1 | `tdd-refactor` | 1.57 | run-04 actual |
| C5 | `one-shot-single` | 2.01 | run-04 actual |
| C7 | `all-tests-first-single` | ~2.50 | **pilot** ($2.39 on `fare`) |
| C4 | `continuous-split` | 2.81 | run-04 actual |
| C6 | `one-shot-split` | 2.85 | run-04 actual |
| C8 | `all-tests-first-split` | ~3.77 | **pilot** ($3.60 on `fare`) |
| | **per task × trial (7 cells)** | **~$16.5** | |

| trials/cell | cells | **est. campaign cost** |
|---|--:|--:|
| 6 | 168 | **~$400** |
| 8 | 224 | **~$530** |
| 12 | 336 | **~$790** |

Recommended: start at **6 trials/cell (~$400)** and sequentially extend only the cells whose
maintainability/test-quality-per-dollar ranking is still ambiguous. The two test-first-split
cells (C8) are the most expensive; the single-agent cells are 2–4× cheaper.

## Eliminated from prompt 06 (won't help this question)

- The stability / variance-ratio contrast, the churn→blast mediation, and the ±5% TOST — all
  were about *refactoring cadence*, now fixed.
- **Part B** (the 20–40-task expansion) — it funded the 5% blast main effect, which is not the
  question here.

## Run plan

1. **Validate** with `--skip-dispatch` (free) — confirms all 7 arms run end-to-end.
2. **1-task cost pilot** on the new arms (`--task fare --arm all-tests-first-single --arm
   all-tests-first-split --trials 1`) to get real per-cell cost.
3. **Campaign:** 7 arms × 4 tasks (`fare`, `payroll`, `cart`, `grades`) × clear specs ×
   N trials. Start at ~6 trials/cell with a sequential extension only for cells whose ranking
   is still ambiguous. Hold the model fixed (`claude-sonnet-4-6`) and report it.

## Guardrails (carried from run 04)

1. Hide acceptance suites during build/change; validate each against a reference first.
2. The invariant is enforced by reverting test edits in refactor steps — it held at 0 violations
   in 364 cells.
3. Hold the model fixed and report it.
4. The task is the unit of inference; with 4 tasks, report per-task and pooled, and be honest
   about what 4 tasks can and cannot resolve.
