# Experiment 05 — Which Agentic Workflow Yields Maintainable, Well-Tested Code at Minimum Cost

**Status:** base campaign complete (672/672 rows, 168/168 cells). Ranking of the top
two workflows is statistically resolved; ranking among the remaining five is not
(see [Ranking ambiguity](#ranking-ambiguity)) — and, per the recommendation below,
resolving it further is not worth funding.

**Data:** [`data/refactor-workflow-matrix.jsonl`](data/refactor-workflow-matrix.jsonl)
**Model:** `claude-sonnet-4-6` (held fixed across all arms)
**Harness:** [`scripts/run_refactor_experiment.py`](../../scripts/run_refactor_experiment.py),
orchestrated by [`scripts/run_workflow_matrix.py`](../../scripts/run_workflow_matrix.py)

---

## The question

> To achieve code that is **maintainable, well structured, and tested with good
> tests at minimum cost**, which agentic workflow works best?

## Bottom line

**`continuous-single`** (write code, then tests, in small per-behavior batches, one
agent) is the clear winner on quality-per-dollar, with **`tdd-refactor`** (classic
Kent Beck TDD, one agent) a clear second. Both are statistically separated from
every other arm and from each other. The remaining five arms cluster together at
roughly 1/4 to 1/5 the efficiency of the leaders, and **the data cannot — and does
not need to — resolve their relative order**: none of them is a workflow worth
recommending, so ranking "which loser loses less" has no decision value. See
[Recommendation](#recommendation).

---

## The four workflows

Two crossed factors define the design space:

| factor | levels |
|---|---|
| **Test/code ordering** | test-first / test-after |
| **Batch size** | small (incremental, per-behavior) / big (all-at-once) |

Crossing them gives four named workflows:

| Workflow | Ordering × batch | Description |
|---|---|---|
| **W1 — Classic TDD** (Kent Beck) | test-first × small | For each behavior: write one failing test (RED), the minimum code to pass it (GREEN), then refactor before the next behavior. |
| **W2 — Code-first, small batches** | test-after × small | For each behavior: write the code, then the test covering it, keeping the suite green; refactor after each green. |
| **W3 — All code, then all tests** | test-after × big | Write the entire implementation first, then the entire test suite in one pass; refactor after the whole thing is green. |
| **W4 — All tests, then code** | test-first × big | Write the entire failing test suite first (no production code exists yet), then write production code until the whole suite passes; refactor after green. |

A third factor, **authorship**, crosses each workflow with:

- **1 agent** — a single agent writes both code and tests.
- **2 agents, context-isolated** — one agent writes tests, a separate agent (with
  no visibility into the tester's reasoning) writes production code, so the coder
  cannot lean on test-writing context and vice versa.

**W1 × 2 agents is excluded by design.** Beck's RED-GREEN-REFACTOR loop is a
single integrated cycle; splitting it across two context-isolated agents is
either heavy-handoff ping-pong or is no longer TDD. That leaves **7 cells**
(not 8):

| Cell | Workflow × authorship | Harness arm |
|---|---|---|
| C1 | W1 × 1 agent | `tdd-refactor` |
| C3 | W2 × 1 agent | `continuous-single` |
| C4 | W2 × 2 agents | `continuous-split` |
| C5 | W3 × 1 agent | `one-shot-single` |
| C6 | W3 × 2 agents | `one-shot-split` |
| C7 | W4 × 1 agent | `all-tests-first-single` |
| C8 | W4 × 2 agents | `all-tests-first-split` |

Refactoring is **mandatory in every arm** — after every green (per-behavior for
the small-batch workflows, once for the big-batch workflows). This was a variable
in earlier experiment iterations; the current design fixes it "on" and removes it,
because "does refactoring help" is a settled question this experiment isn't
re-litigating. Spec clarity is likewise fixed to **clear** (no ambiguity in
requirements) for the same reason.

---

## Methodology

### Tasks (the corpus)

Four small, fully-specified calculator tasks, each with zero judgment calls left
to the implementing agent (every business rule is stated explicitly):

| Task | Spec |
|---|---|
| `fare` | Transit fare calculator — `fare(distance_km, passenger, peak)` → integer cents |
| `payroll` | Payroll net-pay calculator — `net_pay(gross_cents, filing_status, retirement_pct)` → integer cents |
| `cart` | Shopping cart checkout calculator — `checkout(items)` → integer cents |
| `grades` | Weighted gradebook calculator — `final_grade(categories)` → `(percent, letter)` |

Each task ships a **golden starting repo**, a clear spec, and a **3-change
chain** — three sequential follow-up specs applied after the initial build, used
to measure changeability (blast radius) under realistic evolution rather than
only at first-build time.

### Cell execution

Each **cell** = one (task, arm, trial) combination. A cell runs:

1. **build** — implement the initial spec per the arm's workflow definition
2. **change1, change2, change3** — apply three follow-up specs in sequence,
   each against the code left behind by the previous stage

Every stage is dispatched as one or more `claude` CLI invocations (single-agent
arms: one dispatch per stage; split-authorship arms: a tester dispatch, then a
coder dispatch, or vice versa for test-first). Each cell runs in a fully isolated
git worktree with a scratch `$HOME`, so no cell can see another cell's state.

### The tests-frozen invariant

The one hard rule enforced across every arm: **a refactor step must never change
test behavior.** For arms with a separate refactor dispatch (`one-shot`,
`all-tests-first`), this is enforced mechanically — any test-file edits the
refactor step attempted are reverted to the pre-refactor ("green") snapshot
before grading, and the attempted churn is recorded. For arms with refactoring
inlined into the main dispatch (`tdd-refactor`, `continuous-single`), the same
check runs on the refactor-tagged commits, since those cannot be physically
reverted mid-dispatch. **Result: 0 violations across all 672 rows.** The
invariant held perfectly in every cell.

### Trials and campaign scale

- **6 trials per cell** in the base campaign (672 rows = 7 arms × 4 tasks × 6
  trials × 4 stages/cell)
- Trials can be **sequentially extended** (up to a 12-trial ceiling) for any arm
  whose cost-efficiency ranking is still statistically ambiguous after the base
  batch — see [Ranking ambiguity](#ranking-ambiguity)

### Outcome measures

| Goal | Measured by |
|---|---|
| **Tested with good tests** | Mutation score (operator-swap mutants killed / total), CORE + EDGE acceptance-suite pass, test-smell counts (assertless tests, mock density, sleep calls) |
| **Maintainable / well structured** | Blast radius (lines changed in production code per follow-up spec — a proxy for changeability) |
| **Minimum cost** | `cost_usd` from the `claude` CLI's own usage reporting, summed per cell |

**A measurement limitation to disclose:** the static-analysis maintainability
probes (`radon` for cyclomatic complexity / maintainability index, `lizard` for
CCN/token counts, `coverage.py` for branch coverage) were unavailable in the
execution environment for this run, so those fields are `null` across all 672
rows. The **maintainability** half of the quality composite is therefore driven
entirely by **blast radius** (changeability across the 3-change chain), not by
static complexity metrics. The **test-quality** half is intact (mutation score
and CORE/EDGE pass are both fully populated). This narrows what "maintainable"
means in this report to *how much production code churns when requirements
change*, not *how complex the code looks by static metrics*. A rerun with
`radon`/`lizard`/`coverage` installed would sharpen — but is unlikely to
overturn — the ranking below, since blast radius and static complexity are
correlated in practice.

### Quality composite and efficiency frontier

Per arm, raw metrics are averaged across all cells, then combined into a single
quality score in `[0, 1]`:

- **Test-quality component** (mutation score, CORE pass, EDGE pass — coverage
  omitted per the limitation above): equally-weighted mean of available parts.
- **Maintainability component** (blast radius only, per the limitation above):
  min-max normalized across arms and inverted (lower churn = higher score).
- **Composite** = 0.5 × test-quality + 0.5 × maintainability.

**Efficiency** = composite quality ÷ mean cost per cell. A bootstrap (300
resamples per arm, resampling that arm's own cells) produces a standard error
per arm's efficiency estimate, used to test whether adjacent arms' rankings are
statistically distinguishable.

---

## Results

### Raw metrics by arm

| Arm | Workflow | n cells | Mean cost/cell | Mutation score | Core+Edge pass | Mean blast radius (LOC churned/change) | Invariant violations |
|---|---|--:|--:|--:|--:|--:|--:|
| `continuous-single` | W2, 1 agent | 24 | $0.99 | 0.863 | 100% | 40.0 | 0 |
| `tdd-refactor` | W1, 1 agent | 24 | $1.59 | 0.799 | 100% | 39.7 | 0 |
| `one-shot-single` | W3, 1 agent | 24 | $2.09 | 0.934 | 100% | 51.5 | 0 |
| `all-tests-first-single` | W4, 1 agent | 24 | $2.31 | 0.978 | 100% | 51.0 | 0 |
| `one-shot-split` | W3, 2 agents | 24 | $2.99 | 0.976 | 100% | 49.6 | 0 |
| `continuous-split` | W2, 2 agents | 24 | $3.07 | 0.957 | 100% | 51.6 | 0 |
| `all-tests-first-split` | W4, 2 agents | 24 | $4.41 | 0.955 | 100% | 50.9 | 0 |

Every arm hit **100% CORE + EDGE acceptance pass** and **zero invariant
violations** — the harness's hard guardrails held everywhere. The differentiator
is entirely **cost vs. blast radius vs. mutation score**, not correctness.

### Efficiency frontier (quality per dollar)

| Rank | Arm | Workflow | Cost/cell | Quality | **Qual/$** | SE | Ambiguous? |
|--:|---|---|--:|--:|--:|--:|:--:|
| **1** | **`continuous-single`** | **W2, 1 agent** | **$0.99** | **0.961** | **0.968** | 0.084 | **No** |
| **2** | **`tdd-refactor`** | **W1, 1 agent** | **$1.59** | **0.966** | **0.608** | 0.036 | **No** |
| 3 | `one-shot-single` | W3, 1 agent | $2.09 | 0.495 | 0.237 | 0.035 | Yes |
| 4 | `all-tests-first-single` | W4, 1 agent | $2.31 | 0.525 | 0.228 | 0.035 | Yes |
| 5 | `one-shot-split` | W3, 2 agents | $2.99 | 0.582 | 0.195 | 0.026 | Yes |
| 6 | `continuous-split` | W2, 2 agents | $3.07 | 0.493 | 0.160 | 0.027 | Yes |
| 7 | `all-tests-first-split` | W4, 2 agents | $4.41 | 0.523 | 0.119 | 0.022 | Yes |

### Ranking ambiguity

Ambiguity is defined as: an arm's efficiency ±1 SE band overlaps an adjacent
arm's band, meaning the current sample size (n=24 cells/arm) cannot statistically
distinguish their order.

- **`continuous-single` (rank 1) and `tdd-refactor` (rank 2) are each cleanly
  separated** — from each other and from every arm below them. Their bootstrap SEs
  (0.084 and 0.036) are small enough, and the efficiency gap to the next arm
  (0.968 → 0.608 → 0.237) is large enough, that no plausible amount of
  additional trials would reorder the top two, or knock either out of the top two.
- **Ranks 3 through 7 are mutually ambiguous.** Their efficiency scores span a
  narrow band (0.119–0.237) with overlapping confidence intervals — the design's
  sequential-extension rule would flag all five for +3 trials (up to a 12-trial
  ceiling) to try to resolve their internal order.

### Why we are not extending the ambiguous arms

The five ambiguous arms (`one-shot-single`, `all-tests-first-single`,
`one-shot-split`, `continuous-split`, `all-tests-first-split`) are all
**one-quarter to one-fifth as cost-efficient as the winner** and roughly
**one-third as efficient as the runner-up**. Even the best-case reordering among
them — however more trials shuffled their internal ranks — could not lift any of
them past `tdd-refactor`, let alone `continuous-single`; the gap is too large
relative to their measured spread. Since none of the five is a workflow anyone
would recommend adopting, **resolving their internal order has no decision
value** — it would only answer "which losing workflow loses the least," which
doesn't change what a team should do. Extending trials on these five arms is
therefore not worth funding; the ~$400–$790 a full extension would cost is
better spent validating the top two on a larger/harder corpus (see
[Future work](#future-work)) than on sharpening a ranking among options that are
all inferior.

---

## Interpretation

**What made the top two win:**

- **`continuous-single`** (code-first, small batches, one agent) is cheapest
  ($0.99/cell) and keeps blast radius among the lowest (40.0 LOC/change) — small
  batches with immediate refactoring appear to keep the codebase in a state where
  follow-up changes stay localized, and a single agent avoids the coordination
  tax split-authorship arms pay.
- **`tdd-refactor`** (classic TDD) is the second cheapest ($1.59/cell) with
  essentially the same blast radius (39.7) — the discipline of writing one test
  at a time before code doesn't cost much extra over code-first, and the
  refactor-every-cycle habit produces comparably localized changes.

**What hurt the other five:**

- **Big-batch workflows (W3, W4) cost roughly 2–4.5× more per cell** than the
  small-batch workflows, without a compensating jump in mutation score high
  enough to offset the composite's maintainability half — writing an entire
  spec's implementation or entire test suite in one shot, then reconciling, is
  more expensive and doesn't localize changes as well as incremental batches.
- **Split authorship costs more everywhere it's used** (`continuous-split` vs.
  `continuous-single`: $3.07 vs. $0.99; `one-shot-split` vs. `one-shot-single`:
  $2.99 vs. $2.09; `all-tests-first-split` vs. `all-tests-first-single`: $4.41 vs.
  $2.31) without a consistent maintainability payoff — the two-agent
  context-isolation tax (handoff dispatches, redundant re-reading of the spec)
  is not recouped by whatever independence-of-thought benefit it might provide.

**Test quality (mutation score) does not track cost-efficiency.** The
big-batch and split arms actually post *higher* mutation scores (0.93–0.98) than
the two winners (0.80–0.86) — writing an entire test suite up front or with a
dedicated tester agent produces more thorough tests. But this doesn't matter for
the composite ranking because the maintainability half (blast radius) and the
cost denominator dominate: more thorough tests bought at 2–4× the cost and with
worse changeability is not a good trade under this experiment's definition of
"best."

---

## Recommendation

**Use `continuous-single`** (code-first, small per-behavior batches, one agent,
refactor after each green) as the default agentic workflow for tasks resembling
this corpus — small, fully-specified units with a realistic follow-up change
chain. **`tdd-refactor`** (classic TDD) is a reasonable second choice, particularly
if a team has process reasons to prefer test-first discipline; it costs ~60% more
per cell for statistically indistinguishable maintainability and slightly lower
mutation coverage.

**Do not spend further campaign budget** distinguishing the remaining five
workflows from each other. They are all inferior to the top two on the metric
this experiment optimizes for (quality per dollar), by a margin the current
sample already resolves with confidence. Any of them chosen for other reasons
(e.g., an organizational mandate for a specific process) should expect to pay
roughly 2–4.5× the cost of `continuous-single` for the same or worse
changeability.

---

## Limitations

1. **No static-complexity data.** `radon`/`lizard`/`coverage` were unavailable in
   this run's execution environment; maintainability is measured via blast
   radius alone (see [Methodology](#methodology)).
2. **Four tasks.** The task is this experiment's unit of inference; with four
   tasks, cross-task ranking stability is bounded by task count. All four tasks
   are small, fully-specified calculators — the ranking may not generalize to
   larger, more architecturally complex work (see [Future work](#future-work)).
3. **Model held fixed** at `claude-sonnet-4-6`. Results are specific to this
   model; a different model's relative aptitude for incremental vs. big-batch
   work could shift the ranking.
4. **Wall-clock campaign duration** (176+ hours elapsed) was dominated by
   execution-environment instability (a shared container repeatedly reclaimed
   for inactivity, killing in-flight dispatches) rather than actual compute
   time; this affected campaign logistics only; it did not affect correctness of
   the recorded results, since the harness's resume logic guarantees each cell's
   four stages are either fully recorded or not recorded at all.

## Future work

Per the original experiment design, a larger-corpus follow-up (same 7 cells, same
question) would strengthen external validity without re-opening settled
questions:

- **Larger multi-file tasks** — 3–5 source modules behind a public API, not
  single-module calculators.
- **Longer change horizon** — an 8-change chain instead of 3, so changeability
  differences compound and are easier to detect.
- **Held-out changeability probe** — after the change chain, apply two identical
  changes with refactoring disabled, to isolate the changeability each workflow
  "paid forward" via its refactoring discipline.
- **Re-enable static-complexity metrics** — install `radon`/`lizard`/`coverage`
  in the execution environment so the maintainability composite reflects
  complexity, not only blast radius.

This would be a materially larger and more expensive campaign; per the original
design, specify trial count from a power calculation on this run's per-task
variance before funding it.
