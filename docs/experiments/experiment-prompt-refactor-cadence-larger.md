# Experiment Prompt: Does refactoring pay off on larger code over a longer change horizon?

**Type:** Reusable experiment prompt (hand this whole file to Claude to execute)
**Harness:** [`scripts/run_refactor_experiment.py`](../../scripts/run_refactor_experiment.py) — **extend it** (see "Extend the harness")
**Motivation + prior run:** [`refactor-granularity-report.md`](refactor-granularity-report.md)
(the first run; read its **Limitations** section first — this design exists to remove them)

**Status: specified, NOT run.** This is the follow-up the first run's report recommends.

---

## Why a second run

The first refactoring-cadence run held its methodology cleanly — **0 invariant
violations in 364 cells**, confirming that "tests never change during refactoring" is
enforceable — but it could **not** answer whether refactoring pays off, for three
reasons the report names:

1. **Blast conflated cost with benefit.** Cumulative blast counted the refactoring's
   own churn, so refactor arms scored "less changeable" *by construction*; the
   hypothesized payoff (smaller *later* changes) was swamped within a 3-change window.
2. **Tasks were too small and clear.** Single-module features (MI ≈ 75, coverage
   saturated at ~100%) left no room for refactoring to improve structure or for the
   quality sensors to discriminate.
3. **Four tasks underpowered small effects.** The unit of inference is the task.

This run fixes all three: **larger multi-file tasks, a longer change horizon, a
held-out no-refactor change that isolates changeability, and far more tasks.**

---

## Prompt

> Run a controlled experiment on whether refactoring cadence and code/test authorship
> improve changeability and test quality **on larger code over a longer change
> horizon**, holding the validated invariant that refactoring never changes tests.
> Extend `scripts/run_refactor_experiment.py` (do not rebuild it). Work on a feature
> branch; commit the harness extension, the new task corpus, raw data, and the report;
> do not open a PR unless asked.
>
> **Factors (unchanged from the corrected first run):**
> - **granularity**: none / one-shot (single pass) / continuous (per increment)
> - **authorship**: single (one agent writes code+tests) / split (independent coder + tester)
> - plus **`tdd-refactor`** (test-first, continuous, single) as the reference. **7 arms.**
> - **Invariant (every arm):** a refactor step restructures production code only; any
>   test-file edit it makes is reverted to the pre-refactor snapshot.
>
> **The three fixes:**
> 1. **Larger tasks** — multi-file packages (3–5 source modules behind a public API),
>    big enough that structure matters and the quality sensors don't saturate.
> 2. **Longer change horizon** — an **8-change** chain, each modifying behavior, so a
>    cleanup can pay back over later changes.
> 3. **Held-out changeability probe** — after the chain, apply **two identical
>    "probe" changes to every arm with refactoring disabled**, and measure *their*
>    blast. This is the clean changeability outcome: how cheaply does each arm's
>    *accumulated* code absorb a new requirement, with no refactor churn mixed in.
>
> **Decompose blast** at every stage into **change-churn** (lines to satisfy the
> requirement) vs **refactor-churn** (lines the cleanup added), reported separately so
> the *cost* of refactoring is never confused with its *benefit*.
>
> **Scale for power:** **12–16 larger tasks × ~10 trials × 7 arms.** Pre-register N
> from a power calc on the first run's per-task blast variance.

---

## Pre-registered hypotheses (fix before any data)

- **payoff hypothesis (the one the first run couldn't test):** on larger code over an
  8-change horizon, refactoring arms (one-shot, continuous) absorb the **held-out probe
  changes** with lower blast than `none` — i.e. cleanup makes later change cheaper once
  there is enough code and enough horizon for it to matter. **Null:** probe-change blast
  is equal across granularity (refactoring buys no measurable changeability even here).
- **cadence hypothesis:** continuous refactoring yields lower probe-change blast and/or
  better modularity (radon MI, lizard) than one-shot, holding authorship constant.
- **break-even hypothesis:** cumulative *refactor-churn* exceeds the *change-churn
  savings* on early changes but the sign flips by some change index K; estimate K (the
  horizon at which refactoring starts paying for itself), or report that it never flips.
- **authorship hypothesis:** an independent tester (split) raises mutation score / EDGE
  on larger tasks where a single author's blind spots are bigger — or, as in the first
  run, buys nothing and costs ~3×. (First-run prior: no benefit; re-test at larger scale.)

---

## Design

| factor | levels |
|---|---|
| granularity | none / one-shot / continuous |
| authorship | single / split |
| reference | `tdd-refactor` (test-first, continuous, single) |

7 arms × 12–16 tasks × ~10 trials. Each cell:
**build → 8-change chain → 2 held-out probe changes (refactoring disabled, all arms identical).**

Clear specs only (as validated). The invariant and its revert-based enforcement carry
over unchanged from `run_refactor_experiment.py`.

---

## Tasks — the biggest change (author these first)

Each task is a **multi-file package**, not a single-module kata, large enough that
refactoring has something to bite and the quality sensors can move:

- **Shape:** a public API module + 3–5 internal modules (e.g. a parser + evaluator +
  formatter; a rules engine with strategy modules; a small in-memory store with
  index/query/serialize layers). ~150–400 LOC at build, room to grow over 8 changes.
- **Build spec:** clear, ≥ 8 CORE behaviors spanning multiple modules.
- **Change chain (8):** each modifies behavior and is designed so a *monolithic* design
  pays escalating blast while a *modular* design stays localized — the trap that makes
  refactoring's payoff visible. Order changes so early ones are cheap and later ones
  stress cross-module boundaries.
- **Held-out probes (2):** withheld changes of the same character as the chain, applied
  with refactoring disabled in **every** arm, used only to measure changeability.
- **Hidden acceptance:** CORE + per-change + per-probe suites, **validated green against
  a reference solution before running** (as in the first run's `fare`/`payroll`/etc.).
- **Quantity:** author **12–16** such tasks (the unit of inference is the task; this is
  the fix for the first run's power problem). Distinct domains; no overlap with the
  first run's four.

Suggested domains: mini-spreadsheet (cells+formulas+eval), template engine
(parse+render+partials), task scheduler (deps+topo+cycles), json-pointer
(parse+resolve+patch), ledger (accounts+postings+report), url-router
(patterns+match+reverse), query filter (parse+plan+apply).

---

## Extend the harness

Build on `run_refactor_experiment.py` (the arms, the invariant, the revert
enforcement, and the radon/lizard/mutation/coverage/smell sensors all carry over). Add:

1. **Multi-file task support** — the corpus loader and `prod_files()` already handle
   multiple `*.py`; confirm blast/radon/lizard aggregate across modules. Add a manifest
   schema for multi-module golden packages.
2. **8-change chain + 2 held-out probes** — extend `changeChain` and add a `probes`
   list run with refactoring force-disabled for every arm (reuse the `none`-granularity
   change path regardless of the arm's own granularity).
3. **Decomposed blast** — record per stage: **change-churn** (numstat of the change
   dispatch's commits) and **refactor-churn** (numstat of the `refactor:` commits),
   separately, on production files. Cumulate each across the chain. Probe-change blast
   is recorded on its own.
4. **Per-change-index series** — emit blast per change index (not just cumulative) so
   the break-even index K is estimable.
5. **Validate with `--skip-dispatch`** before spending, then a 1-task pilot for cost.

---

## Analysis plan (pre-registered)

- **Primary — changeability:** held-out **probe-change blast**, per arm, paired by task
  (median across trials → compare across the 12–16 tasks). This is the clean outcome the
  first run lacked. Test granularity (none vs one-shot vs continuous) and the cadence
  contrast.
- **Break-even:** plot cumulative (refactor-churn) vs cumulative (change-churn saved
  relative to `none`) across change index; report K or "never."
- **Modularity / test quality:** radon MI, lizard, mutation, coverage across granularity
  — now expected to discriminate on larger code; flag any sensor still saturated.
- **Authorship:** split vs single on probe-change blast, mutation, EDGE, and cost.
- **Cost of quality:** every quality figure raw **and** per-dollar; name the efficient
  frontier.
- **Power:** size trials from the first run's per-task blast SD; the task count (12–16)
  is the real lever — pre-register it and the stopping rule.

---

## What each outcome would mean

| result | interpretation |
|---|---|
| Probe-change blast: refactor < none | Refactoring **does** pay off once code is large and the horizon is long enough — the first run's null was a tasks/horizon artifact. Recommend refactoring; report the break-even K. |
| Probe-change blast equal across granularity | Refactoring's changeability payoff is not real even at scale — a strong, surprising result. Choose cadence on cost alone. |
| Continuous < one-shot on probe blast / MI | Refactor in small steps; cadence matters independently. |
| Authorship still null | Confirm the first run: independent test authorship not worth ~3× cost. |

## Guardrails (carried from the first run)

1. **Hide acceptance during build/change**; validate every acceptance suite against a
   reference before running.
2. **The invariant is enforced by reverting test edits in refactor steps** — keep it;
   it held at 0 violations in 364 cells.
3. **Hold the model fixed and report it.**
4. **Probes must be refactoring-disabled for every arm**, or they stop being a clean
   changeability probe.
5. **Pre-register N, the stopping rule, and the analysis** before any dispatch; the task
   is the unit of inference.

## Expected deliverables

- 12–16 larger multi-file tasks with reference-validated hidden acceptance + 2 probes each.
- Harness extension: multi-file support, 8-change chain + probes, decomposed
  change-/refactor-churn, per-index blast series — proven under `--skip-dispatch`.
- Raw data + one report whose **primary** result is held-out probe-change blast by arm,
  the break-even K, and the three axes raw + per-dollar.
