# Recommendations — The End-to-End Agentic Workflow

Evidence-backed guidance for running an agentic development workflow from
requirements definition through shipped code, synthesizing the best results
from the full experiment line (Experiments 01–05 plus the production
validation in
[`complexity-refactor-regression.md`](../complexity-refactor-regression.md)).
Each recommendation cites the experiment that resolved it; the narrative arc
behind them is in [`README.md`](README.md), and the terminal statistical
result is [`05-final-results.md`](05-final-results.md).

**The workflow in one paragraph:** invest in requirements clarity *before* any
code is written — no downstream workflow recovers information the spec never
stated. Then build with **Code-First Small Batches (Single Agent)**: one agent
writes the code for one behavior, then its test, then refactors while the
suite stays green, and repeats. Keep refactoring on every small batch — never
deferred to the end — and never let a refactor step change a test. Skip
independent coder/tester splits and all-at-once batching; they cost 2–4.5×
more for the same or worse outcomes. Reserve the full plan/review pipeline for
large, multi-file work, where its overhead becomes a minor surcharge and its
enforced review loop is the one lever that measurably improves structure.

---

## 1. Define the requirements first — clarity is irreducible

**Recommendation:** state every business rule explicitly before implementation
begins. Resolve ambiguities with a human conversation (design interrogation,
spec review), not by hoping a disciplined workflow will surface them.

**Evidence:**

- **No workflow compensates for a vague spec.** Under vague requirements, no
  arm recovered information the spec never stated — one task's vague spec
  omitted per-channel retry semantics, and *every* workflow scored 0% on the
  acceptance tests probing that omitted decision. This is a communication
  problem, not a methodology problem
  ([`02-final-results.md`](02-final-results.md)).
- **Spec-synthesis pipelines don't fix it either.** The hypothesis that the
  full `/specs`→`/plan`→`/build` pipeline's explicit acceptance-criteria
  synthesis would surface unstated edge cases better than TDD's failing-test
  discipline was rejected: run to completion, the ship arm scored 25% pooled
  EDGE pass under vague specs vs. Classic TDD's 33% — matching or trailing on
  every task (Experiment 03, reported in
  [`02-final-results.md`](02-final-results.md)).
- The expected clarity×workflow interaction never materialized — workflow
  choice mattered the same amount whether the spec was clear or vague. Fixing
  the spec is a separate, prior investment that no downstream choice
  substitutes for (Experiment 02).

**In practice:** treat the spec the way Experiments 04 and 05 did — they fixed
spec clarity to "clear" because vague specs irreducibly cap what any workflow
can achieve. Aim for the corpus standard: zero judgment calls left to the
implementing agent.

## 2. Size the task before choosing orchestration

**Recommendation:** match the machinery to the work. For small, well-specified
tasks, dispatch a single agent directly. Reserve the full plan/build/review
pipeline for large, multi-file work.

**Evidence:**

- The pipeline's cost premium over the cheapest hand-driven arm **shrinks as
  tasks grow** — 4.74× on small katas, 2.57× on medium features, 1.33× on
  large multi-file packages. Its fixed planning/review overhead is a large
  multiplier on a one-function change and a minor surcharge on a real feature
  ([`01-final-results.md`](01-final-results.md)).
- On the large tier, the pipeline produced the **cleanest code** by the
  review-agent lens (67 weighted findings vs. 91 test-after, 108 test-first) —
  directional at n=6, but the only quality signal in the whole line that
  separated the arms (Experiment 01).

## 3. Build with code-first small batches, one agent

**Recommendation:** default to **Code-First Small Batches (Single Agent)**
(harness arm `continuous-single`): for each behavior, write the code, then the
test covering it, keep the suite green, refactor, move to the next behavior.
**Classic TDD** (`tdd-refactor`) is a sound second choice for teams that
prefer test-first discipline — it costs ~60% more per unit of work for
statistically indistinguishable maintainability.

**Evidence:**

- In the full workflow matrix (test ordering × batch size × authorship),
  Code-First Small Batches (Single Agent) is the clear winner on
  quality-per-dollar ($0.99/cell, quality 0.961, efficiency 0.968), with
  Classic TDD a clear second ($1.59/cell, efficiency 0.608). Both are
  statistically separated from every other arm and from each other; the
  remaining five arms are ¼–⅕ as cost-efficient
  ([`05-final-results.md`](05-final-results.md)).
- **Test-first ordering by itself buys nothing.** It never separated from
  test-after on quality in Experiment 01, and removing just the refactor step
  from TDD erased its changeability advantage entirely — 701 mean lines
  changed vs. test-after's 700 (Experiment 02). The ordering is a preference;
  the refactoring is the mechanism.

**Avoid:**

- **Big batches.** Writing the entire implementation and then the entire test
  suite (or all tests first, then all code) costs 2–4.5× more per cell and
  produces measurably worse changeability (blast radius ~50 vs. ~40 LOC per
  follow-up change) (Experiment 05).
- **Split authorship.** An independent tester agent context-isolated from the
  coder costs ~3× the single-agent equivalent everywhere it was tried, with no
  consistent quality gain — its marginally higher mutation scores never offset
  the coordination tax (Experiments 04 and 05).

## 4. Refactor on every small batch — never only at the end

**Recommendation:** refactor immediately after each green increment, as part
of the loop. Do not accumulate a refactoring debt to pay in one end-of-build
pass, and never skip the step.

**Evidence:**

- **Refactoring is the load-bearing mechanism** of every workflow that won.
  TDD-with-refactor produced the most changeable code across a 3-change chain
  (664 mean lines vs. 700–770 for all other arms), and deleting just the
  refactor step erased the advantage (Experiment 02).
- **Per-batch beats end-of-build.** Both Experiment 05 winners refactor after
  every green; every arm that deferred refactoring to a single final pass
  landed in the inferior cluster. Experiment 04 found the same ordering among
  cadences (continuous 138.5 cumulative blast vs. one-shot 155.0).
- **Don't misread Experiment 04's "no refactoring scored best" row.** That
  result is an artifact of its metric — cumulative blast charged the
  refactor's own churn against the refactoring arms, and a 3-change horizon is
  too short for the payoff to surface (documented in that report's
  limitations). Experiment 05 treated "does refactoring help" as settled and
  made it mandatory in every arm ([`04-final-results.md`](04-final-results.md),
  [`05-final-results.md`](05-final-results.md)).
- **This works in production, not just the harness.** Wiring
  `refactor-opportunity-review`/`complexity-review` into the TDD skill's
  REFACTOR step (Epic P1, PR #378) dropped mean complexity findings below the
  pre-wiring baseline of ~5.3
  ([`complexity-refactor-regression.md`](../complexity-refactor-regression.md)).

**Invariant:** a refactor step must never change test behavior. Refactoring is
behavior-preserving by definition; tests are frozen during it. This is
enforceable mechanically and held perfectly in both campaigns — zero
violations across Experiment 04's 364 cells and Experiment 05's 672 rows.

## 5. Use review agents — not coverage — as the design signal

**Recommendation:** gate structural quality with an enforced review/refactor
loop. Do not use coverage or mutation score to choose between workflows.

**Evidence:**

- **Coverage and mutation are blind to workflow choice.** Every arm saturates
  near 100% coverage / 1.0 mutation on small and medium tasks; even the large
  tier showed the arms landing on top of each other (Experiment 01).
- **Higher mutation scores did not mean better workflows.** The losing
  big-batch and split arms posted *higher* mutation scores (0.93–0.98) than
  the two winners (0.80–0.86) — thoroughness bought at 2–4× the cost with
  worse changeability is a bad trade (Experiment 05).
- The review-agent lens (SRP, complexity, coupling, duplication) was the one
  axis that separated arms on quality (Experiment 01), and its enforced use in
  the REFACTOR step is validated in production
  ([`complexity-refactor-regression.md`](../complexity-refactor-regression.md)).

---

## Scope and caveats

These recommendations rest on the experiment line's stated limits — apply
judgment where your work falls outside them:

- **Corpus:** small-to-medium, fully-specified, mostly single-module tasks
  with a 3-change follow-up chain. A larger-corpus follow-up (multi-file
  tasks, 8-change chain, held-out changeability probe) is scoped but not
  funded ([`05-final-results.md`](05-final-results.md), Future work).
- **Model:** all results at `claude-sonnet-4-6`, held fixed. A different
  model's aptitude for incremental vs. big-batch work could shift rankings.
- **Maintainability proxy:** Experiment 05's maintainability half is blast
  radius (production-code churn per change), not static complexity metrics,
  which were unavailable in that run.
- **Human developers untested.** The design-discovery claim for a *human*
  writing tests one-by-one on open-ended work is outside what this line can
  adjudicate (see [`FAQ.md`](FAQ.md)).
