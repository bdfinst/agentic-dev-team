# Experiment Prompt: Refactoring cadence & authorship — re-aimed at the effects the data can actually resolve

**Type:** Reusable experiment prompt (hand this whole file to Claude to execute)
**Harness:** [`scripts/run_refactor_experiment.py`](../../scripts/run_refactor_experiment.py) — **extend it** (see "Extend the harness")
**Derived from:** [`refactor-granularity-power-analysis.md`](refactor-granularity-power-analysis.md)
(the pre-run power calc — read it first; this prompt *is* its recommendation, made runnable)
**Prior run:** [`refactor-granularity-report.md`](refactor-granularity-report.md) (run 04, clear specs only)
**Companion follow-up:** [`05-experiment-prompt-refactor-cadence-larger.md`](05-experiment-prompt-refactor-cadence-larger.md)
(the larger-code/longer-horizon design — Part B here folds it in)

**Status: specified, NOT run.** Supersedes the headline of run 04's design.

---

## Why re-aim

The power analysis (`python3 scripts/power_calc_refactor_granularity.py`, no model cost)
shows run 04's headline — a **±5% TOST on cumulative blast radius** — is **underpowered by
construction**, and no number of trials fixes it:

| quantity | value |
|---|---|
| grand-mean cumulative blast radius | 701 lines |
| 5% effect target | **35 lines** |
| paired diff per task×clarity | mean **+36**, SD **235** |
| paired units available (4 tasks × 2 clarities) | **8** |
| paired units needed for 80% power @ 5% | **352** |

**The binding constraint is task count, not trials.** The unit of inference is the
task×clarity cell, and there are only 8; per-cell differences swing **−238 → +381 lines**
(~7× the effect we want) and *flip sign with clarity*. Adding trials shrinks each cell's
noise but adds no paired units, so it cannot rescue the main-effect test.

But the same pilot data contains **large, detectable** effects — they are just not the 5%
main effect. The 664-vs-678 "tie" is an artifact of averaging a sign-flipping,
heteroscedastic distribution. Cell-by-cell:

**1. Free (one-shot) refactor is wildly unstable — a ~7× variance effect:**

| arm | within-cell SD of cumulative blast |
|---|--:|
| tdd-refactor (continuous, frozen-ish) | 29.5 |
| test-after (no refactor) | 24.1 |
| tdd-no-refactor | 14.5 |
| **test-after-refactor (one-shot, free)** | **208.1** |

**2. Free refactor destroys edge coverage under vague specs — a huge EDGE effect:**

| arm | EDGE pass rate, vague spec |
|---|--:|
| test-after | 66.7% |
| bduf | 41.7% |
| tdd-refactor | 33.3% |
| ship / tdd-no-refactor | 25.0% |
| **test-after-refactor** | **0.0%** |

These are exactly the **safety-net hypothesis** (safety-net erosion) and
**authorship-interaction hypothesis** (clarity×protection interaction) mechanisms the
earlier work hypothesized, and at 7× variance and 0%-vs-67% EDGE they sit far above the
5% noise floor — **detectable at modest N on the current four tasks.** This prompt promotes
them to primary and demotes the blast-radius equivalence claim to an honestly-underpowered
secondary.

---

## Two parts, run in order

**Part A — re-aim on the current corpus (cheap, do this first).** Reuse the four clean-room
tasks (`fare`, `payroll`, `cart`, `grades`) and the seven arms. **Re-introduce the
clear/vague clarity crossing** that run 04 dropped — it is the axis the EDGE collapse lives
on — and run **~12–15 trials/cell** to pin the high-variance free-refactor cells. Answer the
variance, EDGE, and churn-mediation questions the data *can* settle now.

**Part B — expand for the 5% main effect (expensive, only if it must stay primary).** The
blast-radius main effect needs **task count, not trials**: author **20–40 pays-style tasks**
(and, converging with [`05-experiment-prompt-refactor-cadence-larger.md`](05-experiment-prompt-refactor-cadence-larger.md),
prefer larger multi-file tasks over a longer change horizon with decomposed change-/refactor-churn).
Part B is a much larger campaign; do not start it before Part A reports.

---

## Prompt

> Run a controlled experiment on refactoring cadence and code/test authorship, **re-aimed at
> the variance, edge-coverage, and churn-mediation effects** the prior pilot shows are
> resolvable — not the 5% blast-radius main effect, which is underpowered at four tasks.
> Hold the validated invariant that refactoring never changes tests (revert any test edit a
> refactor step makes). Extend `scripts/run_refactor_experiment.py` (do not rebuild it). Work
> on a feature branch; commit the harness extension, raw data, and the report; do not open a
> PR unless asked.
>
> **Arms (unchanged, 7):** granularity none / one-shot / continuous × authorship single /
> split, plus `tdd-refactor` (test-first, continuous, single) as the reference.
>
> **PART A — current corpus, re-aimed (run first):**
> 1. **Re-introduce clarity** — cross every cell with **clear** and **vague** specs. The
>    EDGE collapse only appears under vague specs; run 04's clear-only design hid it.
> 2. **~12–15 trials/cell** — enough to estimate each cell's *within-cell variance* stably
>    (the free one-shot arm's SD ≈ 208 needs ~10+ trials for a stable median/spread).
> 3. **Primary endpoints (promoted):**
>    - **(a) Stability / variance contrast:** within-cell SD (and IQR) of cumulative blast,
>      free (one-shot) vs frozen (continuous / tdd-refactor / none). Test the variance ratio
>      (Levene / Brown–Forsythe), not just the means. Pre-registered expectation: free ≫ frozen.
>    - **(b) EDGE collapse under free + vague:** EDGE pass rate per arm × clarity. Pre-registered
>      expectation: test-after-refactor (free) collapses toward 0% under vague while frozen
>      arms hold; report the clarity×granularity interaction explicitly.
>    - **(c) Churn → blast mediation:** does **test-LOC churn** during change mediate cumulative
>      blast radius? Record test-file churn and production blast per change and fit the
>      mediation (or report the correlation and partial correlation if N is too small to fit).
> 4. **Secondary endpoint (demoted, reported honestly):** the ±5% TOST on cumulative blast.
>    Pre-register that it will most likely read **"inconclusive at this scale"** and report it
>    that way — do not bury the underpowering.
>
> **PART B — expand for the 5% main effect (only if it must stay primary):**
> Author **20–40** pays-style tasks (the binding limitation is task count, not trials), or
> adopt the larger multi-file / longer-horizon design of the companion `05` prompt with
> decomposed change-churn vs refactor-churn. Pre-register N from a power calc on the prior
> per-task blast variance. This is a separate, much larger campaign.
>
> **Validate with `--skip-dispatch`, then a 1-task pilot for cost, before spending.**

---

## Pre-registered hypotheses (fix before any data)

- **stability hypothesis (primary):** free (one-shot) refactor has materially higher
  within-cell blast variance than frozen cadences (continuous, tdd-refactor, none) — pilot
  prior ≈ 7× SD. **Null:** variance ratio ≈ 1 (cadence does not affect stability).
- **safety-net hypothesis (primary):** under **vague** specs, free refactor erodes the test
  safety net and collapses EDGE pass rate toward 0% while frozen arms retain it — pilot prior
  0% vs 25–67%. **Null:** EDGE pass is equal across granularity within the vague cells.
- **authorship-interaction hypothesis (primary):** the protection effect interacts with
  clarity — the free-vs-frozen EDGE gap is large under vague specs and small/absent under
  clear specs (run 04 saw EDGE ≈ CORE under clear-only). **Null:** no clarity×granularity
  interaction.
- **churn-mediation hypothesis (primary):** test-LOC churn during change mediates cumulative
  blast radius (more test churn → more downstream blast). **Null:** blast is independent of
  test churn once the change is held fixed.
- **5% blast-radius equivalence (secondary, expected inconclusive):** continuous and one-shot
  refactor are equivalent within ±5% on cumulative blast. Pre-registered: **underpowered at
  four tasks; report as inconclusive unless Part B expands the corpus.**

---

## Design

| factor | levels |
|---|---|
| granularity | none / one-shot / continuous |
| authorship | single / split |
| **clarity (re-introduced)** | **clear / vague** |
| reference | `tdd-refactor` (test-first, continuous, single) |

**Part A:** 7 arms × 4 tasks × 2 clarities × ~12–15 trials. The invariant and its
revert-based enforcement carry over unchanged from run 04 (0 violations in 364 cells).

**Part B:** same factors, **20–40 tasks** (or the `05` larger-task corpus), trial count sized
from a fresh power calc; the task is the unit of inference.

---

## Extend the harness

Build on `run_refactor_experiment.py` (arms, the invariant, the revert enforcement, and the
radon / lizard / mutation / coverage / smell sensors all carry over). Add:

1. **Clarity crossing** — restore the clear/vague spec variants per task (the prior tdd-pays
   harness already had vague specs; port the vague spec text and the EDGE-under-vague grading).
2. **Per-cell variance capture** — emit within-cell SD and IQR of cumulative blast (not just
   the median) so the stability contrast and Levene/Brown–Forsythe test are computable.
3. **Per-change churn series** — record **test-LOC churn** and **production blast** separately
   per change index, so the churn→blast mediation is estimable.
4. **EDGE × clarity breakdown** — report EDGE pass rate split by arm × clarity, not pooled.
5. **TOST as a secondary, labeled output** — keep the ±5% equivalence test but tag it
   `underpowered_at_N` with the achieved power, so the report cannot present it as decisive.
6. **Validate with `--skip-dispatch`**, then a 1-task pilot, before any campaign spend.

---

## Analysis plan (pre-registered)

- **Primary — stability:** within-cell SD/IQR of cumulative blast, free vs frozen; variance-ratio
  test (Levene/Brown–Forsythe). Report the ratio and CI.
- **Primary — EDGE collapse:** EDGE pass rate, arm × clarity, with the clarity×granularity
  interaction called out; free+vague vs everything else.
- **Primary — mediation:** test-LOC churn → cumulative blast; fit the mediation or report
  correlation + partial correlation (controlling for change index) if N is small.
- **Secondary — equivalence:** ±5% TOST on cumulative blast, reported with achieved power and
  an explicit "inconclusive at this scale" verdict unless Part B ran.
- **Cost of quality:** every quality figure raw **and** per-dollar; name the efficient frontier
  (run 04 prior: split authorship ≈ 3× cost for no measurable gain — re-confirm under the
  clarity crossing).
- **Power:** for Part B, size the task corpus from the prior per-task blast SD; pre-register N
  and the stopping rule. The task is the unit of inference.

---

## What each outcome would mean

| result | interpretation |
|---|---|
| Free blast variance ≫ frozen | Cadence matters for **stability**, not just mean blast — one-shot/free refactoring is unpredictable. Prefer frozen/continuous on risk grounds even where means tie. |
| EDGE collapses under free + vague | Confirms **safety-net erosion**: a big one-shot refactor under an under-specified spec silently drops edge behavior. Strong argument for continuous, test-anchored refactoring. |
| Clarity×granularity interaction present | The protection benefit is **conditional on spec ambiguity** — refactoring discipline pays most exactly when requirements are vague. |
| Test churn mediates blast | Churning tests during change *causes* downstream blast — operationalizes "keep tests stable." |
| 5% TOST inconclusive (expected) | The headline equivalence claim is **not answerable at four tasks**; only Part B's 20–40-task corpus can settle it. Report honestly; do not over-claim a "tie." |

---

## Guardrails

1. **Hide acceptance during build/change**; validate every acceptance suite against a reference
   before running (as in run 04's `fare`/`payroll`/`cart`/`grades`).
2. **The invariant is enforced by reverting test edits in refactor steps** — keep it; it held
   at 0 violations in 364 cells.
3. **Hold the model fixed and report it** (`claude-sonnet-4-6` in the prior runs).
4. **Report the secondary TOST with its achieved power** — never present an underpowered
   equivalence test as a decisive "tie."
5. **Pre-register N, the stopping rule, and the analysis** before any dispatch; the task is the
   unit of inference, and trials cannot substitute for tasks on the main effect.

## Expected deliverables

- Harness extension: clarity crossing restored, per-cell variance capture, per-change test-churn
  vs production-blast series, EDGE×clarity breakdown, TOST labeled `underpowered_at_N` — proven
  under `--skip-dispatch`.
- Part A raw data (7 arms × 4 tasks × 2 clarities × ~12–15 trials) + one report whose **primary**
  results are the free-vs-frozen variance ratio, the EDGE collapse under free+vague, and the
  churn→blast mediation — with the ±5% equivalence reported as a clearly-labeled, underpowered
  secondary.
- A go/no-go recommendation on **Part B** (the 20–40-task expansion) based on whether the 5%
  main effect is still worth its much larger cost after Part A.
