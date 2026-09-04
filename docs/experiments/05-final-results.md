# Final Results — Which Agentic Workflow Yields Maintainable, Well-Tested Code at Minimum Cost

**Status: FINAL.** Base campaign complete (672/672 rows, 168/168 cells). Ranking of
the top two workflows is statistically resolved; ranking among the remaining five is
not (see [Ranking ambiguity](#ranking-ambiguity)) — and, per the recommendation below,
resolving it further is not worth funding. This is the terminal report for the
refactor-cadence/workflow-matrix experiment line (experiments 01–05); see
[`README.md`](README.md) for the full narrative arc.

**Data:** [`agentic-workflow-evidence/data/refactor-workflow-matrix.jsonl`](agentic-workflow-evidence/data/refactor-workflow-matrix.jsonl)
**Model:** `claude-sonnet-4-6` (held fixed across all arms)
**Harness:** [`scripts/run_refactor_experiment.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/scripts/run_refactor_experiment.py),
orchestrated by [`scripts/run_workflow_matrix.py`](https://github.com/bdfinst/agentic-dev-team/blob/main/scripts/run_workflow_matrix.py)

---

## The question

> To achieve code that is **maintainable, well structured, and tested with good
> tests at minimum cost**, which agentic workflow works best?

## Bottom line

Seven workflow arms were compared, each defined by test/code ordering × batch
size × authorship (see [The four workflows](#the-four-workflows) for the full
factor definitions). This report refers to each arm by a descriptive name; the
kebab-case harness arm ID in parentheses is what appears in the raw data files
and scripts, and is unchanged there.

- **Classic TDD** (`tdd-refactor`) — classic Kent Beck TDD: for each behavior,
  write one failing test, the minimum code to pass it, then refactor before the
  next behavior; one agent writes code and tests.
- **Code-First Small Batches (Single Agent)** (`continuous-single`) — code-first
  in small per-behavior batches: write the code for one behavior, then its test,
  refactor after each green; one agent.
- **Code-First Small Batches (Split Authorship)** (`continuous-split`) — the
  same small-batch code-first loop, but tests are written by a separate,
  context-isolated agent.
- **All Code, Then All Tests (Single Agent)** (`one-shot-single`) — write the
  entire implementation first, then the entire test suite, with a single
  refactor pass at the end; one agent.
- **All Code, Then All Tests (Split Authorship)** (`one-shot-split`) — the same
  all-code-then-all-tests flow, with a separate context-isolated test author.
- **All Tests, Then Code (Single Agent)** (`all-tests-first-single`) — write the
  entire failing test suite first, then production code until it all passes,
  with a single refactor pass at the end; one agent.
- **All Tests, Then Code (Split Authorship)** (`all-tests-first-split`) — the
  same all-tests-then-code flow, with a separate context-isolated test author.

**Code-First Small Batches (Single Agent)** is the clear winner on
quality-per-dollar, with **Classic TDD** a clear second. Both are statistically separated from
every other arm and from each other. The remaining five arms cluster together at
roughly 1/4 to 1/5 the efficiency of the leaders, and **the data cannot — and does
not need to — resolve their relative order**: none of them is a workflow worth
recommending, so ranking "which loser loses less" has no decision value. See
[Recommendation](#recommendation).

**On refactoring cadence specifically: refactor on every small batch, not once
at the end.** Both winning workflows refactor after each green increment; every
arm that defers refactoring to a single end-of-build pass costs 2–4.5× more per
cell and leaves the code measurably less changeable (blast radius ~50 vs. ~40
LOC per follow-up change). Experiment 04's raw numbers should not be read as
"skip refactoring": its blast metric charged the refactor's own churn against
the refactoring arms and its 3-change horizon was too short for the payoff to
surface (see that report's limitations). This experiment fixed refactoring "on"
in every arm for exactly that reason, and among cadences, per-batch refactoring
wins.

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
| **W2 — Code-First Small Batches** | test-after × small | For each behavior: write the code, then the test covering it, keeping the suite green; refactor after each green. |
| **W3 — All Code, Then All Tests** | test-after × big | Write the entire implementation first, then the entire test suite in one pass; refactor after the whole thing is green. |
| **W4 — All Tests, Then Code** | test-first × big | Write the entire failing test suite first (no production code exists yet), then write production code until the whole suite passes; refactor after green. |

A third factor, **authorship**, crosses each workflow with:

- **1 agent** — a single agent writes both code and tests.
- **2 agents, context-isolated** — one agent writes tests, a separate agent (with
  no visibility into the tester's reasoning) writes production code, so the coder
  cannot lean on test-writing context and vice versa.

**W1 × 2 agents is excluded by design.** Beck's RED-GREEN-REFACTOR loop is a
single integrated cycle; splitting it across two context-isolated agents is
either heavy-handoff ping-pong or is no longer TDD. That leaves **7 cells**
(not 8):

| Cell | Workflow name | Workflow × authorship | Harness arm |
|---|---|---|---|
| C1 | Classic TDD | W1 × 1 agent | `tdd-refactor` |
| C3 | Code-First Small Batches (Single Agent) | W2 × 1 agent | `continuous-single` |
| C4 | Code-First Small Batches (Split Authorship) | W2 × 2 agents | `continuous-split` |
| C5 | All Code, Then All Tests (Single Agent) | W3 × 1 agent | `one-shot-single` |
| C6 | All Code, Then All Tests (Split Authorship) | W3 × 2 agents | `one-shot-split` |
| C7 | All Tests, Then Code (Single Agent) | W4 × 1 agent | `all-tests-first-single` |
| C8 | All Tests, Then Code (Split Authorship) | W4 × 2 agents | `all-tests-first-split` |

The **Workflow name** column is how this report refers to each arm; the
**Harness arm** ID is the identifier recorded in
[`refactor-workflow-matrix.jsonl`](agentic-workflow-evidence/data/refactor-workflow-matrix.jsonl)
and used by the harness scripts, which are unchanged.

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
test behavior.** For arms with a separate refactor dispatch (the big-batch
workflows — All Code, Then All Tests and All Tests, Then Code), this is enforced
mechanically — any test-file edits the refactor step attempted are reverted to
the pre-refactor ("green") snapshot before grading, and the attempted churn is
recorded. For arms with refactoring inlined into the main dispatch (Classic TDD
and Code-First Small Batches (Single Agent)), the same
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

| Workflow | Harness arm | n cells | Mean cost/cell | Mutation score | Core+Edge pass | Mean blast radius (LOC churned/change) | Invariant violations |
|---|---|--:|--:|--:|--:|--:|--:|
| Code-First Small Batches (Single Agent) | `continuous-single` | 24 | $0.99 | 0.863 | 100% | 40.0 | 0 |
| Classic TDD | `tdd-refactor` | 24 | $1.59 | 0.799 | 100% | 39.7 | 0 |
| All Code, Then All Tests (Single Agent) | `one-shot-single` | 24 | $2.09 | 0.934 | 100% | 51.5 | 0 |
| All Tests, Then Code (Single Agent) | `all-tests-first-single` | 24 | $2.31 | 0.978 | 100% | 51.0 | 0 |
| All Code, Then All Tests (Split Authorship) | `one-shot-split` | 24 | $2.99 | 0.976 | 100% | 49.6 | 0 |
| Code-First Small Batches (Split Authorship) | `continuous-split` | 24 | $3.07 | 0.957 | 100% | 51.6 | 0 |
| All Tests, Then Code (Split Authorship) | `all-tests-first-split` | 24 | $4.41 | 0.955 | 100% | 50.9 | 0 |

Every arm hit **100% CORE + EDGE acceptance pass** and **zero invariant
violations** — the harness's hard guardrails held everywhere. The differentiator
is entirely **cost vs. blast radius vs. mutation score**, not correctness.

### Efficiency frontier (quality per dollar)

| Rank | Workflow | Harness arm | Cost/cell | Quality | **Qual/$** | SE | Ambiguous? |
|--:|---|---|--:|--:|--:|--:|:--:|
| **1** | **Code-First Small Batches (Single Agent)** | `continuous-single` | **$0.99** | **0.961** | **0.968** | 0.084 | **No** |
| **2** | **Classic TDD** | `tdd-refactor` | **$1.59** | **0.966** | **0.608** | 0.036 | **No** |
| 3 | All Code, Then All Tests (Single Agent) | `one-shot-single` | $2.09 | 0.495 | 0.237 | 0.035 | Yes |
| 4 | All Tests, Then Code (Single Agent) | `all-tests-first-single` | $2.31 | 0.525 | 0.228 | 0.035 | Yes |
| 5 | All Code, Then All Tests (Split Authorship) | `one-shot-split` | $2.99 | 0.582 | 0.195 | 0.026 | Yes |
| 6 | Code-First Small Batches (Split Authorship) | `continuous-split` | $3.07 | 0.493 | 0.160 | 0.027 | Yes |
| 7 | All Tests, Then Code (Split Authorship) | `all-tests-first-split` | $4.41 | 0.523 | 0.119 | 0.022 | Yes |

### Ranking ambiguity

Ambiguity is defined as: an arm's efficiency ±1 SE band overlaps an adjacent
arm's band, meaning the current sample size (n=24 cells/arm) cannot statistically
distinguish their order.

- **Code-First Small Batches (Single Agent) (rank 1) and Classic TDD (rank 2)
  are each cleanly separated** — from each other and from every arm below them. Their bootstrap SEs
  (0.084 and 0.036) are small enough, and the efficiency gap to the next arm
  (0.968 → 0.608 → 0.237) is large enough, that no plausible amount of
  additional trials would reorder the top two, or knock either out of the top two.
- **Ranks 3 through 7 are mutually ambiguous.** Their efficiency scores span a
  narrow band (0.119–0.237) with overlapping confidence intervals — the design's
  sequential-extension rule would flag all five for +3 trials (up to a 12-trial
  ceiling) to try to resolve their internal order.

### Why we are not extending the ambiguous arms

The five ambiguous arms (both All Code, Then All Tests variants, both All
Tests, Then Code variants, and Code-First Small Batches (Split Authorship)) are all
**one-quarter to one-fifth as cost-efficient as the winner** and roughly
**one-third as efficient as the runner-up**. Even the best-case reordering among
them — however more trials shuffled their internal ranks — could not lift any of
them past Classic TDD, let alone Code-First Small Batches (Single Agent); the gap is too large
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

- **Code-First Small Batches (Single Agent)** is cheapest
  ($0.99/cell) and keeps blast radius among the lowest (40.0 LOC/change) — small
  batches with immediate refactoring appear to keep the codebase in a state where
  follow-up changes stay localized, and a single agent avoids the coordination
  tax split-authorship arms pay.
- **Classic TDD** is the second cheapest ($1.59/cell) with
  essentially the same blast radius (39.7) — the discipline of writing one test
  at a time before code doesn't cost much extra over code-first, and the
  refactor-every-cycle habit produces comparably localized changes.

**What hurt the other five:**

- **Big-batch workflows (W3, W4) cost roughly 2–4.5× more per cell** than the
  small-batch workflows, without a compensating jump in mutation score high
  enough to offset the composite's maintainability half — writing an entire
  spec's implementation or entire test suite in one shot, then reconciling, is
  more expensive and doesn't localize changes as well as incremental batches.
- **Split authorship costs more everywhere it's used** (Code-First Small
  Batches: $3.07 split vs. $0.99 single; All Code, Then All Tests: $2.99 split
  vs. $2.09 single; All Tests, Then Code: $4.41 split vs.
  $2.31 single) without a consistent maintainability payoff — the two-agent
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

**Use Code-First Small Batches (Single Agent)** (write code, then tests, in
small per-behavior batches, one agent,
refactor after each green) as the default agentic workflow for tasks resembling
this corpus — small, fully-specified units with a realistic follow-up change
chain. **Classic TDD** is a reasonable second choice, particularly
if a team has process reasons to prefer test-first discipline; it costs ~60% more
per cell for statistically indistinguishable maintainability and slightly lower
mutation coverage.

**Refactor on every small batch, not only at the end.** This is the shared trait
of the two winners and the answer to the cadence question this experiment line
set out to settle: refactoring after each green increment keeps follow-up
changes localized, while deferring all refactoring to one end-of-build pass
(the W3/W4 arms) costs more and produces worse changeability. Experiment 04's
apparent "no refactoring scored best" result is an artifact of its metric and
short change horizon (documented in its limitations section), not a reason to
skip the refactor step.

**Do not spend further campaign budget** distinguishing the remaining five
workflows from each other. They are all inferior to the top two on the metric
this experiment optimizes for (quality per dollar), by a margin the current
sample already resolves with confidence. Any of them chosen for other reasons
(e.g., an organizational mandate for a specific process) should expect to pay
roughly 2–4.5× the cost of Code-First Small Batches (Single Agent) for the same
or worse changeability.

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
