# TDD Experiment — FAQ

Questions and answers about the TDD experiment findings. See the reports for
detail: [`3sizes-3arms-report.md`](3sizes-3arms-report.md) (three-arm study),
[`tdd-vs-nontdd-report.md`](tdd-vs-nontdd-report.md) (TDD vs non-TDD), and the
follow-up design [`ambiguous-requirements-experiment.md`](ambiguous-requirements-experiment.md).

---

## Q1. How do the findings align with the claim that a main goal of TDD is design discovery — "by writing tests one after the other, you are gradually discovering the design that you feel is optimal"?

**Short answer:** the findings don't support that claim and lean mildly against
it — but the experiment is a *weak test* of it, and the way it fails is itself
informative.

### What the claim predicts vs. what we saw
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

### Why the experiment can't really adjudicate the claim
The claim is about a *developer gradually discovering* design. The experiment
removed the conditions that benefit lives in:

- **It's an autonomous LLM, not a human.** An agent tends to pattern-match a whole
  solution up front regardless of test order; the incremental "this wants to be a
  different shape" insight the claim describes isn't guaranteed to engage.
- **Requirements were clear and frozen.** Design discovery matters most when the
  design space is open; with a fully-specified spec the optimal shape is largely
  determined — little to discover. (Same scope caveat as the TDD-vs-non-TDD report.)
- **Tasks were small/well-understood**, constraining the design space; the payoff
  for emergent design grows with novelty and size.
- **Design was measured by proxy** (review agents), not the developer's *felt*
  sense of "optimal," which is what the claim is actually about.

### The interesting reconciliation
Design quality **did** improve — but with the **build-pipeline**, which adds an
explicit review/refactor step, not from test ordering. That supports the *spirit*
of the claim (iterating on and critiquing structure yields better design) while
showing the trigger was the deliberate "examine and improve the structure" act,
not the RED-GREEN cadence alone. For an autonomous agent, the design benefit came
from an **enforced refactor/review loop**, not from writing tests one-by-one.

That gap is exactly what **Epic P1** (GitHub #362) targets — wiring
`refactor-opportunity-review`/`complexity-review` into the REFACTOR step. Honest
read: test-first *as run here* did not deliver design discovery, the experiment
cannot refute the claim for a human on open-ended design, and it points at both
*why* (the refactor/insight step was missing) and *how* to make TDD produce it.
