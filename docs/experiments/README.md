# The Agentic Workflow Experiments — Narrative

Five experiments, run in sequence, each answering the question the previous one
left open. This page tells that story end to end; each experiment's own report
has the full methodology and data. **[`05-final-results.md`](05-final-results.md)
is the terminal result** — the answer this whole line of work was building toward.

All experiments hold the model fixed at `claude-sonnet-4-6` and grade against
hidden acceptance tests injected only at grading time, so no arm can see (or
accidentally satisfy) the test it's being judged against.

---

## The arc, in one paragraph

We started by asking the broadest possible question — does the dev-team
`/plan`→`/build` pipeline beat hand-driven TDD or test-after coding at all? —
and found the pipeline's cost premium shrinks as tasks grow, with a directional
quality edge on large work (**Experiment 01**). That pushed us to ask *when*
TDD specifically pays off, which surfaced the real mechanism: it isn't
test-first ordering that matters, it's the **refactor step** — and no workflow
recovers information a vague spec never stated (**Experiment 02**, with a
manual follow-up in **Experiment 03** confirming that even the full
`/specs`→`/plan`→`/build` pipeline doesn't out-perform TDD's failing-test
discipline at surfacing unstated edge cases). That refactoring finding needed
its own dedicated test — cadence (when to refactor) crossed with authorship
(one agent vs. two) — which the first attempt was underpowered to answer
cleanly (**Experiment 04**, corrected mid-flight). The corrected, adequately
powered version of that question, expanded to a full 2×2×2 workflow matrix, is
**Experiment 05** — the final result.

---

## Experiment 01 — Does the full pipeline beat hand-driven coding?

**[`3sizes-3arms-report.md`](3sizes-3arms-report.md)** · design:
[`01-experiment-prompt-3sizes-3arms.md`](01-experiment-prompt-3sizes-3arms.md)

**Question:** Does dev-team's `/plan`→`/build` pipeline produce better or
cheaper code than a single agent doing strict TDD, or a single agent writing
code then tests, at small / medium / large task sizes?

**Design:** 3 workflows (`build-pipeline`, `test-first`, `test-after`) × 3 task
sizes (6 small katas, 6 medium single-module features, 6 large multi-file
packages) = 192 graded cells.

**What we found:**

- The pipeline's cost premium over the cheapest hand-driven arm **shrinks as
  tasks get bigger** — 4.74× at small, 2.57× at medium, 1.33× at large. Its
  fixed planning/review overhead is a large multiplier on a one-function kata
  and a minor surcharge on a real feature.
- **test-first vs. test-after never separated on quality** and barely
  separated on cost, with no consistent direction across sizes.
- **Coverage and mutation score are blind to workflow choice** — every arm
  saturates near 100%/1.0 on small and medium tasks; even the large tier,
  which finally showed some spread (96.6–98.2% coverage, 0.911–0.924 mutation),
  showed the three arms landing on top of each other.
- The one axis that *did* separate the workflows: running dev-team's own
  review agents (structure, complexity, naming, performance, security, test)
  over each arm's output found the **pipeline's code cleanest** (67 weighted
  findings vs. 91 for test-after and 108 for test-first) — directional, not
  conclusive at n=6, but the first quality signal in the whole line that
  pointed anywhere.

**What this motivated:** the review-agent lens was the only thing that moved,
and it pointed at the pipeline's inline review step, not at test-first
ordering. That's what Experiment 02 went to test directly — not "TDD vs.
not-TDD" in the abstract, but *what about TDD's discipline actually produces
the effect*.

*(A precursor covering the small/medium tiers only, run before the large tier
existed, is preserved at [`tdd-vs-nontdd-report.md`](tdd-vs-nontdd-report.md);
its small-tier data was re-run at the fixed model for Experiment 01 rather than
reused, since the precursor used a different model on that tier.)*

---

## Experiment 02 (+ 03) — When does TDD actually pay off?

**[`when-tdd-pays-report.md`](when-tdd-pays-report.md)** · design:
[`02-experiment-prompt-when-tdd-pays.md`](02-experiment-prompt-when-tdd-pays.md) ·
manual follow-up: [`03-ship-arm-manual-run-prompt.md`](03-ship-arm-manual-run-prompt.md)

**Question:** Crossing requirement clarity (clear vs. vague spec) with coding
workflow (TDD-with-refactor, TDD-without-refactor, test-after,
big-design-up-front), on tasks with a deliberate design trap — what combination
actually produces better code, and does TDD compensate for a vague spec?

**Design:** 4 workflows × 2 clarity conditions × 4 open-design tasks × 3
trials = 288 graded dispatches across 72 cells.

**What we found:**

- **TDD does not compensate for a vague spec.** Under vague requirements, no
  workflow recovered information the spec never stated — one task's vague
  spec omitted per-channel retry semantics, and every workflow scored 0% on
  the acceptance tests probing that omitted decision. This is a communication
  problem, not a methodology problem.
- **Refactoring, not test-first ordering, is the mechanism.** TDD-with-refactor
  produced the most changeable code (664 mean lines changed across a 3-change
  chain, vs. 700–770 for every other arm) — but removing just the refactor
  step (`tdd-no-refactor`) erased the advantage entirely (701 lines,
  indistinguishable from test-after's 700). Test-first ordering by itself
  bought nothing; the discipline of refactoring after green is what mattered.
- **The clarity/workflow interaction we expected didn't materialize** — TDD's
  changeability advantage was consistent whether the spec was clear or vague,
  not larger under vague conditions as hypothesized.
- **Experiment 03's manual follow-up rejected the "spec-synthesis" hypothesis**
  that the full `/specs`→`/plan`→`/build` pipeline's explicit
  acceptance-criteria synthesis would surface unstated edge cases better than
  TDD's failing-test discipline. Run to completion outside the harness's
  dispatch timeout, the `ship` arm scored 25% pooled EDGE pass under vague
  spec vs. TDD-refactor's 33% — matching or trailing on every task.

**What this motivated:** refactoring was now confirmed as the load-bearing
mechanism, which raised a sharper question the design hadn't isolated yet —
*how much* refactoring, and *by whom* (one agent vs. two independent
agents)? That's Experiment 04.

---

## Experiment 04 — Refactoring cadence and authorship (corrected mid-flight)

**[`refactor-granularity-report.md`](refactor-granularity-report.md)** · design:
[`04-experiment-prompt-refactor-granularity.md`](04-experiment-prompt-refactor-granularity.md) ·
power analysis: [`refactor-granularity-power-analysis.md`](refactor-granularity-power-analysis.md)

**Question:** Crossing refactor granularity (none / one-shot / continuous) with
authorship (single agent / independent coder+tester), plus a TDD reference arm
— what combination produces the most changeable, well-tested code at the
lowest cost?

**A correction happened before this ran at scale.** The original design
treated "are tests frozen during refactoring" as a variable to cross. A
pre-run power analysis caught that this was conceptually wrong — refactoring
is behavior-preserving by definition, so tests must never change during a
refactor step; that's an invariant every arm must satisfy, not something to
manipulate. The design was corrected to enforce the invariant everywhere
(reverting any test-file edit a refactor step attempted) before any
budget was spent on the flawed version. This is the direct methodological
ancestor of the tests-frozen invariant that later ran clean across all 672
rows of Experiment 05.

**Design (corrected):** 7 arms (none/one-shot/continuous × single/split, plus
tdd-refactor) × 4 tasks × 13 trials = 364 cells.

**What we found:**

- **The tests-frozen invariant held perfectly — 0 violations across 364
  cells.** The corrected methodology worked as designed.
- **Refactoring did not pay back within a 3-change horizon on these tasks.**
  Cumulative blast radius rose monotonically with refactoring effort — none
  (104.5) < continuous (138.5) < one-shot (155.0) — with maintainability index
  essentially flat (72–80) regardless of granularity. On these small,
  clear-spec tasks, cleanup added churn and cost without a measurable
  changeability gain over three changes.
- **Split authorship cost ~3× single-agent with no quality gain** — $0.97 vs.
  $2.84 per cell — and actually posted a slightly *lower* EDGE pass rate (98%
  vs. 100%) despite marginally higher mutation score.
- A named limitation: cumulative blast **conflates change cost with the
  refactor's own churn**, so refactor arms look "less changeable" partly by
  construction — the real question (does refactoring make *later* changes
  smaller?) wasn't cleanly separated by this metric.

**What this motivated:** the "all tests first, then code" workflow (W4 in the
final taxonomy) was still missing from the design, and the blast-radius
metric needed the multi-change chain it already had, just interpreted more
carefully. Experiment 05 folded this experiment's 5 working arms in unchanged,
added the two missing W4 arms, and reframed the whole thing as a clean 2×2×2
factorial (test ordering × batch size × authorship) built to answer one
final, focused question.

*(Related methodology validation, not part of this arc's main question but
built on its findings: [`complexity-refactor-regression.md`](complexity-refactor-regression.md)
confirms `/build`'s inline REFACTOR step, once wired to dispatch
`complexity-review`, dropped mean complexity findings below the pre-wiring
baseline — direct evidence the refactor-step mechanism identified here is
doing real work inside the actual plugin, not just the experiment harness.)*

---

## Experiment 05 — The final answer

**[`05-final-results.md`](05-final-results.md)** · design:
[`05-experiment-prompt-workflow-matrix.md`](05-experiment-prompt-workflow-matrix.md)

**Question:** To achieve code that is maintainable, well-structured, and
tested with good tests **at minimum cost**, which agentic workflow works best?

**Design:** the clean 2×2×2 factorial the whole line was building toward —
test ordering (test-first / test-after) × batch size (small, per-behavior /
big, all-at-once) × authorship (1 agent / 2 context-isolated agents), minus
the one excluded cell (classic TDD split across two agents isn't TDD anymore).
7 arms × 4 tasks × 6 base trials = 672 cells, refactoring mandatory in every
arm (settled by Experiment 02), tests-frozen invariant enforced in every arm
(settled by Experiment 04's correction).

**What we found:**

- **`continuous-single`** (code-first, small per-behavior batches, one agent)
  and **`tdd-refactor`** (classic TDD) are clearly, statistically separated
  winners on quality-per-dollar — cheapest ($0.99 and $1.59/cell), lowest
  blast radius, and their efficiency confidence intervals don't overlap each
  other or anything below them.
- **The other five arms are mutually indistinguishable from each other, but
  uniformly worse than the top two** — 3 to 8× less cost-efficient, big-batch
  and split-authorship workflows costing 2–4.5× more per cell without a
  compensating maintainability gain. Resolving their internal order has no
  decision value, since none of them is a workflow worth recommending anyway.
- **Test quality (mutation score) does not track cost-efficiency** — the
  losing arms actually post higher mutation scores than the two winners, but
  that doesn't matter once blast radius and cost dominate the composite.

**The recommendation:** default to `continuous-single`; `tdd-refactor` is a
reasonable second choice for teams with process reasons to prefer test-first
discipline. See `05-final-results.md` for the full methodology, raw metrics,
limitations, and future-work notes (a larger-corpus follow-up is scoped but
not funded).

---

## What answered what

| Question raised | Where it was answered |
|---|---|
| Does the full pipeline beat hand-driven coding? | 01 |
| Does anything separate workflows on structural quality? | 01 (review-agent lens) → motivated 02 |
| Does TDD compensate for vague requirements? | 02 (no — spec-gap is irreducible) |
| Is TDD's advantage test-first ordering, or refactoring? | 02 (refactoring — isolated by removing it) |
| Does the full `/specs` pipeline out-perform TDD at surfacing unstated decisions? | 03 (no) |
| How much refactoring, by whom? | 04 (corrected mid-flight; refactoring didn't pay back in 3 changes on small tasks; split authorship cost 3× for no gain) |
| Which complete workflow — ordering × batch size × authorship — wins on quality per dollar? | **05 (final): `continuous-single`, then `tdd-refactor`** |

## Supporting documents

- [`FAQ.md`](FAQ.md) — targeted Q&A against specific claims about TDD (e.g.,
  "TDD gradually discovers optimal design"), cross-referencing 01 and 02.
- [`refactor-granularity-power-analysis.md`](refactor-granularity-power-analysis.md) —
  the pre-run correction that caught Experiment 04's design flaw before it ran
  at scale; worth reading as a methodology lesson independent of the results.
- [`complexity-refactor-regression.md`](complexity-refactor-regression.md) —
  confirms the refactor-step mechanism (identified in 02, tested in 04)
  actually improves output when wired into the real `/build` skill, not just
  the experiment harness.
- [`refactor-granularity-progress.md`](refactor-granularity-progress.md) and
  [`refactor-granularity-summary.md`](refactor-granularity-summary.md) —
  plain-language summary and run-progress log for Experiment 04.
