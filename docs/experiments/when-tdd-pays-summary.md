# When Does TDD Actually Pay Off? — Summary

A condensed version of [`when-tdd-pays-report.md`](when-tdd-pays-report.md), which
has the full data, statistics, and method.

**What we tested:** one model (`claude-sonnet-4-6`) built four small Python components
using several coding workflows, under both **clear** and **vague** specs. We then asked
it to make three follow-up changes to each and measured how well it coped.

---

## Terms

- **Clear vs vague spec** — a clear spec states the tricky decisions; a vague spec leaves
  them out, so the model has to infer them.
- **CORE** — behavior the spec stated explicitly. Did it build the right thing?
- **EDGE** — the edge cases and judgment calls the spec omitted. Did it infer them the
  way the hidden acceptance tests expected?
- **Blast radius** — lines of code touched to make the three follow-up changes. Lower
  means the code was easier to change.
- **Workflows compared** — *TDD with refactoring* (failing test → pass → clean up);
  *TDD without refactoring* (no cleanup step); *test-after* (build, then test it);
  *test-after-refactor* (build, test, then clean up); *BDUF* (big design up front);
  *ship* (the dev-team pipeline: `/specs` → `/plan` → `/build`).

---

## Headline

No workflow compensates for a vague spec — a missing decision gets guessed, and often
guessed wrong. Where workflow *does* matter is changeability, and there the deciding
factor is the refactoring step, not test-first ordering.

---

## Findings

### 1. A vague spec is a communication problem

The notifier task omitted one detail (how retries should work). Under the vague spec,
**every workflow scored 0%** on the EDGE tests that depended on it — TDD, test-after,
BDUF alike. Information that was never written down cannot be recovered from the
workflow; it has to come from the spec.

### 2. Under a vague spec, test-after infers edge cases better than TDD

For the omissions that *were* inferable from context:

| EDGE pass rate, vague spec | |
|---|---|
| test-after | 67% |
| TDD with refactoring | 33% |

TDD commits to an interpretation before any working code exists, and that early
commitment tends to be incomplete. test-after builds first, then writes tests that
capture the actual behavior — edge handling included.

### 3. TDD improves changeability, but the refactoring step is what does it

Across the three follow-up changes:

| Workflow | Blast radius |
|---|---|
| TDD with refactoring | 664 |
| test-after | 700 |
| TDD without refactoring | 701 |
| BDUF | 770 |

TDD *without* refactoring (701) lands on top of test-after (700). The advantage comes
from the refactoring, not from writing tests first. Drop the cleanup step and you pay
TDD's higher cost for none of the benefit.

**The two workflows that *do* refactor are a tie.** test-after-refactor scores 678 —
essentially the same as TDD-with-refactoring's 664 (a 2% gap, inside the measurement
noise at this sample size). So the split is clean: the two refactor workflows (664, 678)
sit together, ~5% below the two non-refactor ones (700, 701). Test-first ordering buys
nothing extra once both workflows refactor. This is a second confirmation that
refactoring — not test ordering — is the mechanism, not a contradiction of it. (Whether
the small 664-vs-678 difference is real at all is the open question in the last section.)

### 4. The "ship" pipeline doesn't resolve vagueness

`ship` runs `/specs` to write a detailed specification up front, then `/plan` and
`/build`. The premise was that forcing every decision into an explicit spec would surface
the omitted ones. It didn't: **25%** EDGE under a vague spec, against TDD's 33%.

The mechanism is the notable part. `/specs` produces a thorough-looking document —
requirements, architecture, acceptance criteria, a table of decisions about omitted
behavior, and a self-check that reports "consistent." But it fills that table with
happy-path answers and then certifies itself complete. On the event-store task the
generated spec listed two of the trap decisions explicitly, chose the wrong answer for
both, and marked its consistency gate "passed."

Writing a spec from a vague prompt relocates the guess from the code into the spec. It
reads as more rigorous; it's the same guess.

### 5. test-after-refactor loses edge coverage under a vague spec

This workflow (build → test → clean up) had strong blast radius (within ~2% of the best)
and cost less than TDD, but scored **0%** EDGE under a vague spec — below plain
test-after. The cleanup step rewrote the code and removed the tests that had recorded the
edge-case decisions. It holds up under a clear spec; the refactor step is the liability
when the spec is vague.

### 6. Cost

| Workflow | Cost per stage |
|---|---|
| test-after | $0.19 |
| TDD without refactoring | $0.22 |
| BDUF | $0.24 |
| test-after-refactor | $0.35 |
| TDD with refactoring | $0.44 |

TDD with refactoring runs ~2.3× the cost of test-after, from the iteration in the
test-first loop. That is the price of its changeability advantage.

---

## Recommendations

| Situation | Workflow |
|---|---|
| Vague spec | Clarify the omissions first. No workflow — including auto-generating a detailed spec — recovers a decision that was never made. |
| Clear spec, long-lived code | TDD with refactoring — lowest blast radius. |
| Clear spec, one-shot or cost-sensitive | test-after — comparable quality, ~2.3× cheaper. |
| Cleaner code without TDD's overhead | test-after-refactor, clear spec only (it loses edge coverage under a vague one). |
| Throwaway or speed-first | test-after or TDD without refactoring — same changeability, lowest cost. |

Refactoring is what makes code easier to change; nothing in the workflow substitutes for
resolving what the spec left unstated.

---

## Open question and a proposed next experiment

The two workflows that refactor came out 664 vs 678 on change cost — a 2% difference that
is inside the noise at three trials per cell. We can't yet say whether that small gap is
real or just measurement scatter. If it *is* real, there are two candidate explanations:

1. **How often you refactor.** TDD cleans up in small steps as it goes; test-after-refactor
   does one cleanup pass at the end. Many small cleanups may keep code more malleable than
   one big one.
2. **What the cleanup does to the tests.** test-after-refactor's cleanup step rewrote and
   deleted some of its own tests (the same thing that wiped out its edge-case coverage
   under a vague spec). A thinner test suite is a weaker safety net for later changes.

**Proposed next experiment.** Run a larger study (around 12–15 trials per case instead of
3, enough to tell a real 5% difference from noise) that varies two things independently:
*how often the code is refactored* (continuously vs one pass at the end) and *whether the
tests are allowed to change during the cleanup* (frozen vs free). Track how many lines of
test code the cleanup adds or deletes, so we can see whether test churn is what drives the
difference.

Three outcomes, each useful:

- **The gap disappears** → the two refactor workflows are truly interchangeable on
  changeability; choose between them on cost and edge-case robustness instead.
- **Refactoring continuously wins** → refactor in small steps, whatever the test ordering.
- **Test churn explains it** → protect or regenerate the test suite across a cleanup, and
  the lost edge coverage and the slightly higher change cost turn out to share one cause.

The full pre-registration (hypotheses, the 2×2 design, power, and analysis plan) is in the
report's [refactoring-cadence follow-up](when-tdd-pays-report.md#proposed-follow-up-refactoring-cadence-and-the-test-safety-net).

---

*Summary of [`when-tdd-pays-report.md`](when-tdd-pays-report.md); numbers and method are
in the full report.*
