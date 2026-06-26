# Refactoring cadence & authorship — Summary

A condensed version of [`refactor-granularity-report.md`](refactor-granularity-report.md),
which has the full data, statistics, and method.

**What we tested:** one model (`claude-sonnet-4-6`) built four small Python components
(`fare`, `payroll`, `cart`, `grades`) under **clear** specs, then made a chain of three
follow-up changes to each. We varied *how often the code was refactored* and *who wrote the
tests*, holding fixed the rule that **refactoring never changes tests**. 7 arms × 4 tasks ×
13 trials = **364 cells**.

---

## Terms

- **Granularity** — how often cleanup happens: **none** (never), **one-shot** (a single pass),
  or **continuous** (a little after every change).
- **Authorship** — **single** (one agent writes code and tests) vs **split** (an independent
  agent writes the tests).
- **tdd-refactor** — the reference arm: test-first, continuous cleanup, single author.
- **The invariant** — a refactor restructures production code only; if a cleanup step touches a
  test file, that edit is reverted. "Refactoring is behavior-preserving, so it must not change
  the tests" — enforced, not assumed.
- **Cumulative blast radius** — total lines of code touched to make the three follow-up changes.
  Lower means the code was easier to change.
- **CORE / EDGE** — stated behavior vs inferred edge cases. **MI** — radon maintainability index.

---

## Headline

On small, clear-spec modules over a three-change horizon, **refactoring did not pay for
itself, and an independent test author bought nothing for ~3× the cost.** The result worth
keeping is methodological: treating "tests don't change during refactoring" as an enforced
invariant works cleanly — **0 violations in 364 cells** — and the harness and tasks are
reusable for a fairer follow-up.

---

## Findings

### 1. The corrected methodology held perfectly

No refactor step changed a test across all **364 cells** — any attempted churn was reverted,
and the inline arms attempted none. The "tests stay fixed during a cleanup" rule is
**enforceable** and was respected everywhere. This is the run's most solid result.

### 2. Refactoring didn't pay back within three changes

Cumulative blast rose monotonically with refactoring effort, consistently across all four
tasks:

| Granularity | Cumulative blast | Cost | MI |
|---|--:|--:|--:|
| none | 104.5 | $1.13 | 77.3 |
| continuous | 138.5 | $1.91 | 72.7 |
| one-shot | 155.0 | $2.40 | 75.0 |

Maintainability (MI ≈ 72–80) is essentially flat across cadence. On small, already-simple
modules, cleanup adds churn and cost without a measurable changeability or structural gain
over three changes. **This is by construction as much as by behavior:** blast counts the
refactoring's *own* lines, so refactor arms look "less changeable" partly because the metric
charges them for the cleanup itself (see Limitations).

### 3. Split authorship cost ~3× single, with no quality gain

| Authorship | Cost | Mutation | EDGE |
|---|--:|--:|--:|
| single | $0.97 | 0.95 | 100% |
| split | $2.84 | 1.00 | 98% |

An independent test author roughly tripled cost while moving quality nowhere meaningful —
mutation up a hair, EDGE down a hair. On these tasks it did not earn its price.

### 4. Test quality barely moved

Coverage 90–100%, mutation median 0.92, CORE/EDGE 96–100% across every arm. There was little
room for granularity or authorship to separate — the sensors were near-saturated on tasks
this small and clear.

---

## What this run can and can't tell you

**It settles the method.** "Tests unchanged during refactoring" is enforceable, and the
harness/corpus are sound and reusable.

**It does *not* yet settle whether refactoring pays off**, for four reasons:

1. **Blast conflates cost with benefit** — it counts the cleanup's own churn, so the
   hypothesized payoff (smaller *later* changes) is swamped inside a three-change window.
2. **Tasks were too small and clear** — single-module features (MI ≈ 75, coverage ~100%) leave
   refactoring nothing to bite and the quality sensors nothing to discriminate.
3. **Four tasks underpower small effects** — the unit of inference is the task; four can't
   resolve a ~5% changeability difference (see
   [`refactor-granularity-power-analysis.md`](refactor-granularity-power-analysis.md)).
4. **Clear specs only** — this removes the vague-spec edge-inference signal, so EDGE ≈ CORE here
   by design, hiding the safety-net effect the earlier study found.

The large, consistent effects (refactor churn, split-authorship cost) are real; the small ones
are not resolvable at this scale.

---

## Recommendations

| Situation | Guidance |
|---|---|
| Small, clear-spec, short-horizon changes | Neither extra refactoring cadence nor split authorship earns its cost — `none`/single is the efficient choice here. |
| Choosing a test-authorship model | Independent (split) test authoring is not worth ~3× cost on tasks like these; re-test only at larger scale. |
| Want to actually measure refactoring's payoff | Run a fairer follow-up: larger multi-file tasks, a longer change chain, and a blast metric that separates refactor-churn from change-churn (or a held-out no-refactor change). |
| Trust the invariant | Yes — revert-based enforcement of "tests don't change during refactoring" held at 0/364. |

---

## What's next

Two follow-ups are specified:

- **[`05-experiment-prompt-refactor-cadence-larger.md`](05-experiment-prompt-refactor-cadence-larger.md)** —
  larger multi-file tasks, an 8-change horizon, a held-out changeability probe, and decomposed
  change-/refactor-churn, so refactoring's *payoff* can finally be isolated from its *cost*.
- **[`06-experiment-prompt-refactor-granularity-revised.md`](06-experiment-prompt-refactor-granularity-revised.md)** —
  re-aims the current four-task corpus (clarity crossing restored, ~12–15 trials) at the effects
  the data *can* resolve now: the free-vs-frozen blast-variance contrast, the EDGE collapse under
  free + vague specs, and test-churn → blast mediation — with the underpowered ±5% blast-radius
  equivalence demoted to an honestly-labeled secondary.

---

*Summary of [`refactor-granularity-report.md`](refactor-granularity-report.md); numbers and
method are in the full report.*
