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

*Summary of [`when-tdd-pays-report.md`](when-tdd-pays-report.md); numbers and method are
in the full report.*
