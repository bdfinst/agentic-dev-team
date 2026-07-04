# Refactoring cadence & authorship — results

**Status: complete.** 7 arms × 4 tasks × 13 trials = **364 cells**, clear specs,
build + 3-change chain, model `claude-sonnet-4-6`. Raw data:
[`agentic-workflow-evidence/data/refactor-granularity-merged.jsonl`](agentic-workflow-evidence/data/refactor-granularity-merged.jsonl);
machine summary: [`agentic-workflow-evidence/data/refactor-granularity-summary.json`](agentic-workflow-evidence/data/refactor-granularity-summary.json);
reproduce with `python3 scripts/analyze_refactor_experiment.py`.

**Plain-language summary:** the Experiment 04 section of [`README.md`](README.md).

## Design

Follow-up to the *When Does TDD Pay Off?* finding that two refactoring workflows tied
on changeability. The original draft crossed a "tests free vs frozen during
refactor" factor; that was **corrected** — refactoring is behavior-preserving and must
not change tests, so "tests unchanged during refactor" is an **invariant of every
arm**, not a variable. Enforced by reverting any test-file edit a refactor step makes
back to the pre-refactor snapshot (and recording it). We varied:

- **granularity**: none / one-shot (single pass) / continuous (per increment)
- **authorship**: single (one agent writes code+tests) / split (independent coder + tester)
- plus **tdd-refactor** (test-first, continuous, single) as the reference.

Four clean-room tasks (`fare`, `payroll`, `cart`, `grades`), each with a hidden
CORE/EDGE acceptance suite and a 3-change chain whose trap punishes non-modular code.

## Results (per-arm; blast/cost are medians of the 4 task-medians)

| arm | cum blast | cost $ | blast/$ | mutation | cov % | MI | CORE | EDGE | violations |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| tdd-refactor (ref) | 110.5 | 1.56 | 70.8 | 0.78 | 100 | 76.4 | 100% | 100% | **0** |
| no-refactor-single | **103.5** | **0.73** | 141.8 | 0.95 | 100 | 75.0 | 100% | 100% | 0 |
| one-shot-single | 154.5 | 1.97 | 78.4 | 1.00 | 100 | 75.6 | 96% | 96% | 0 |
| continuous-single | 118.5 | 0.97 | 122.2 | 0.92 | 100 | 71.9 | 100% | 100% | 0 |
| no-refactor-split | 105.5 | 1.53 | 69.0 | 1.00 | 100 | 79.6 | 96% | 96% | 0 |
| one-shot-split | 155.5 | 2.84 | 54.8 | 1.00 | 100 | 74.4 | 98% | 98% | 0 |
| continuous-split | 158.5 | 2.85 | 55.6 | 1.00 | 100 | 73.5 | 98% | 98% | 0 |

**Factor main effects** (test-after grid; reference excluded):

| granularity | cum blast | cost | MI |
|---|--:|--:|--:|
| none | 104.5 | 1.13 | 77.3 |
| one-shot | 155.0 | 2.40 | 75.0 |
| continuous | 138.5 | 1.91 | 72.7 |

| authorship | cum blast | cost | mutation | EDGE |
|---|--:|--:|--:|--:|
| single | 118.5 | 0.97 | 0.95 | 100% |
| split | 155.5 | 2.84 | 1.00 | 98% |

## Findings

**1. The corrected methodology held perfectly — 0 invariant violations in 364 cells.**
No refactor step changed a test (attempted churn was reverted where it occurred; none
was attempted in the inline arms). The "tests don't change during refactoring" rule is
enforceable and was respected.

**2. Refactoring did not pay back within a 3-change horizon on these tasks.** Cumulative
blast rises monotonically with refactoring effort — none (104) < continuous (138) <
one-shot (155) — consistently across all four tasks, and maintainability (MI ≈ 72–80)
is essentially flat across granularity. On small, clear-spec modules the cleanup adds
churn and cost without a measurable changeability or structural gain over three changes.

**3. Split authorship cost ~3× single with no quality gain.** single $0.97 vs split
$2.84 per cell; split's mutation (1.0 vs 0.95) is marginally higher but its EDGE pass is
marginally *lower* (98% vs 100%). An independent test author bought nothing measurable
here while roughly tripling cost.

**4. Test quality barely moved.** Coverage 90–100%, mutation median 0.92, CORE/EDGE
96–100% across every arm — little room for granularity or authorship to separate on
these tasks.

## Limitations (read before drawing strong conclusions)

1. **Blast conflates change-cost with refactor-churn.** Cumulative blast counts the
   refactoring's own line changes, so refactor arms score "less changeable" partly *by
   construction*. The hypothesized payoff — refactoring makes *later* changes smaller —
   is swamped by the cleanup churn within a 3-change window and is not separated in this
   metric. A cleaner test would measure a held-out change made *without* refactoring, or
   record change-churn and refactor-churn separately.
2. **Tasks are small and clear-spec.** Single-module features where the code is already
   simple (MI ~75) leave little room for refactoring to improve structure or for
   coverage/mutation to discriminate. The original premise likely needs larger,
   multi-file tasks and a longer change horizon (6–10 changes) to surface a payoff.
3. **Four tasks → underpowered for small effects.** The unit of inference is the task;
   four is too few to resolve a ~5% changeability difference (see
   [`04-power-analysis.md`](04-power-analysis.md)).
   The large, consistent effects here (refactor churn, split cost) are real; small ones
   are not resolvable.
4. **Clear specs only** removes the vague-spec edge-inference signal that separated arms
   in the prior study, so EDGE ≈ CORE here by design.

## Recommendation

- **Methodologically, the correction is the headline:** treating "tests unchanged during
  refactoring" as an enforced invariant works, and the harness/ corpus are reusable.
- **On these tasks, neither refactoring cadence nor split authorship earns its cost.**
  Refactoring small, already-simple modules over a short change horizon adds churn and
  spend without measurable benefit; split authorship triples cost for no quality gain.
- **To actually test refactoring's changeability payoff**, the next run needs (a) larger
  multi-file tasks, (b) a longer change chain, and (c) a blast metric that separates
  refactor-churn from change-churn (or a held-out no-refactor change). Until then this
  run answers the *methodology* cleanly and the *changeability payoff* only weakly.
