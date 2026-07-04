# TDD Experiment — FAQ

Questions and answers about the TDD experiment findings. See the reports for
detail: [`01-final-results.md`](01-final-results.md) (three-arm study, which
subsumes the earlier two-arm TDD-vs-test-after cut of the same data),
[`02-final-results.md`](02-final-results.md) (the follow-up that isolated
refactoring as TDD's load-bearing mechanism), and
[`05-final-results.md`](05-final-results.md) (the terminal workflow-matrix
result). [`README.md`](README.md) tells the full five-experiment story.

---

## Q1. How do the findings align with the claim that a main goal of TDD is design discovery — "by writing tests one after the other, you are gradually discovering the design that you feel is optimal"?

**Short answer:** the findings don't support the *test-ordering* half of that
claim — writing tests one-by-one bought no measurable design advantage in any
experiment — but they strongly support its *refactoring* half. The design
benefit the claim describes is real, and it comes from the deliberate
refactor-after-green step, not from the RED-GREEN cadence. Experiment 01
suggested this; Experiment 02 confirmed it by isolation; Experiment 05's
winning workflows both have per-batch refactoring as their shared trait.

### What the claim predicts vs. what Experiment 01 saw
If writing tests one-by-one gradually surfaces the optimal design, test-first
should produce the **best-structured** code. The review-grade lens — the only axis
that actually measures design (SRP, complexity, coupling, duplication) — found the
opposite ordering on the large tier (weighted review findings, lower = cleaner):

| Arm | Weighted review findings |
|---|---|
| build-pipeline | 67 (cleanest) |
| test-after | 91 |
| **test-first (TDD)** | **108 (most)** |

Test-first drew the *most* findings, concentrated in `complexity-review` — long,
deeply-nested functions on the parser-heavy tasks. The incremental test-by-test
process did **not** converge on a cleaner design here. (Directional only: n=6,
sign p≈0.38, with real reviewer variance — read it as "no design advantage," not
"test-after wins.")

The mechanism is visible: TDD's design discovery is supposed to happen in
**REFACTOR**, and the agent's strict RED-GREEN-REFACTOR **stopped at GREEN** — it
made tests pass and moved on. No refactor → no emergent design.

### Why Experiment 01 alone couldn't adjudicate the claim
The claim is about a *developer gradually discovering* design. Experiment 01
removed the conditions that benefit lives in:

- **It's an autonomous LLM, not a human.** An agent tends to pattern-match a whole
  solution up front regardless of test order; the incremental "this wants to be a
  different shape" insight the claim describes isn't guaranteed to engage.
- **Requirements were clear and frozen.** Design discovery matters most when the
  design space is open; with a fully-specified spec the optimal shape is largely
  determined — little to discover.
- **Tasks were small/well-understood**, constraining the design space; the payoff
  for emergent design grows with novelty and size.
- **Design was measured by proxy** (review agents), not the developer's *felt*
  sense of "optimal," which is what the claim is actually about.

The human-developer and "felt sense of optimal" caveats still stand — no
experiment in this line tests the claim for a human. The other conditions were
addressed by the follow-ups below: open-design tasks with a deliberate trap,
vague-spec conditions, and changeability measured by a withheld change chain.

### What the follow-up experiments settled

**Experiment 02 ran the test this FAQ originally called for and confirmed the
mechanism by isolation.** On open-design tasks graded by a 3-change chain,
TDD-with-refactor produced the most changeable code (664 mean lines changed
vs. 700–770 for every other arm) — and removing *just* the refactor step
(`tdd-no-refactor`) erased the advantage entirely (701 lines, indistinguishable
from test-after's 700). Test-first ordering by itself bought nothing; the
discipline of refactoring after green is what mattered. See
[`02-final-results.md`](02-final-results.md).

**Experiment 05 closed the arc.** Across the full workflow matrix (test
ordering × batch size × authorship), the two statistically separated winners on
quality-per-dollar — Code-First Small Batches (Single Agent) and Classic TDD —
share one trait: they refactor after every green increment in small batches.
Test ordering did not separate them; every arm that deferred refactoring to a
single end-of-build pass cost 2–4.5× more with worse changeability. See
[`05-final-results.md`](05-final-results.md).

### The reconciliation
Design quality **does** improve — but the trigger is the deliberate "examine and
improve the structure" act, not the RED-GREEN cadence alone. That supports the
*spirit* of the claim (iterating on and critiquing structure yields better
design) while relocating the credit: for an autonomous agent, the design benefit
comes from an **enforced refactor/review loop**, not from writing tests
one-by-one.

That gap has since been closed in the plugin itself. Epic P1 (GitHub #362,
"Make review actually improve the code") wired
`refactor-opportunity-review`/`complexity-review` into the TDD skill's REFACTOR
step (P1-S1, PR #378), and the regression check in
[`complexity-refactor-regression.md`](../complexity-refactor-regression.md)
confirms mean `complexity-review` findings dropped below the pre-wiring
baseline (~5.3) — the refactor-step mechanism identified in these experiments
is doing real work inside the actual `/build` workflow, not just the experiment
harness.

Honest read: test-first *as run in Experiment 01* did not deliver design
discovery; the follow-ups showed why (the refactor step was missing), proved
the mechanism by isolating it (Experiment 02), and validated the fix in
production (Epic P1). The claim remains untested for a human developer on
open-ended design.
