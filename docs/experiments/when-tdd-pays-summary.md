# When Does TDD Actually Pay Off? — Plain-Language Summary

**This is the easy-to-read version.** For the full data, statistics, and method,
see [`when-tdd-pays-report.md`](when-tdd-pays-report.md).

**What we tested:** one AI model (`claude-sonnet-4-6`) building four small Python
components, using several different coding styles, under both **clear** and **vague**
written instructions. Then we asked it to make three follow-up changes to each one and
measured how well it coped.

---

## A few terms, in plain words

- **Clear spec vs vague spec** — a clear spec spells out the tricky decisions; a vague
  spec leaves them unsaid, so the AI has to guess.
- **"The basics" (CORE)** — behavior the spec actually stated. Did it build the right
  thing at all?
- **"The unstated decisions" (EDGE)** — the edge cases and judgment calls the spec left
  out. Did the AI guess them the way we intended?
- **"Change cost" (blast radius)** — how many lines of code it had to touch to make the
  three follow-up changes. Fewer lines = code that was easier to change.
- **The coding styles we compared:**
  - **TDD with refactoring** — write a failing test, make it pass, then clean up.
  - **TDD without refactoring** — write a failing test, make it pass, skip the cleanup.
  - **test-after** — build it first, then write tests against what you built.
  - **test-after-refactor** — build it, test it, then clean it up.
  - **BDUF** — big design up front, then build.
  - **ship** — use the dev-team pipeline: `/specs` (write down the requirements in
    detail) → `/plan` → `/build`.

---

## The big picture

**No coding style can rescue a vague spec.** If the instructions leave out a decision,
every style just guesses — and often guesses wrong. The fix is not a better workflow;
it's a quick conversation to nail down what was missing.

**Where the workflow *does* matter is changeability.** TDD pays off when code has to keep
changing over time — but only because of the *cleanup (refactoring)* step, not because
tests come first.

---

## The findings, one at a time

### 1. A vague spec is a communication problem, not a coding problem

The clearest result in the whole study: the **notifier** task left out one detail (how
retries should work). Under the vague spec, **every single style scored 0%** on the
edge-case tests that depended on that detail. TDD, test-after, big-design-up-front — all
0%. You cannot recover information that was never written down.

**Takeaway:** When a spec is vague, stop and ask. A clarifying question costs minutes;
guessing wrong costs a rewrite later.

### 2. When the spec is vague, "test-after" guesses better than TDD

For the cases where the missing detail *could* be reasonably inferred, writing tests
**after** building beat test-first:

| Edge-case score under a vague spec | |
|---|---|
| test-after | **67%** |
| TDD with refactoring | 33% |

Why? TDD locks in an interpretation *before* there's any working code to react to — and
that early guess is often incomplete. test-after builds something real first, then writes
tests that capture what it actually does, edge cases included.

### 3. TDD makes code easier to change — but only the cleanup step matters

Across the three follow-up changes, "change cost" (lines touched) was lowest for TDD with
refactoring:

| Coding style | Change cost (fewer = better) |
|---|---|
| **TDD with refactoring** | **664** |
| test-after | 700 |
| TDD *without* refactoring | 701 |
| big design up front | 770 |

Notice that TDD **without** the cleanup step (701) is basically the same as test-after
(700). So the benefit isn't "tests first" — it's the **refactoring**. Skip the cleanup
and you pay TDD's higher cost for none of the benefit.

### 4. The "ship" pipeline (write the spec in detail first) doesn't fix vagueness either

The `ship` style uses the dev-team pipeline: `/specs` writes out a detailed specification
first, then `/plan` and `/build`. The idea was that forcing the AI to write down every
decision up front would surface the missing ones.

It didn't. Under a vague spec it scored **25%** on edge cases — no better than TDD (33%).

**Why it fails is the interesting part.** `/specs` *does* produce a thorough-looking
document — requirements, architecture, a full list of acceptance criteria, even a table
of "decisions we're making about things the spec left out," and a self-check that says
"all consistent." But it fills that table with the *easy, happy-path* answers — and then
certifies itself as complete.

For the event-store task, the AI's own spec explicitly wrote down two of the trap
decisions and chose the **wrong** answer for both — then stamped the document
"consistency check: passed." It didn't overlook the decision; it noticed it, guessed
wrong, and signed off confidently.

**Takeaway:** Writing a detailed spec from a vague prompt just **moves the guess from the
code into the spec**. It looks more rigorous, but it's the same guess — now dressed up as
a finished document.

### 5. "test-after-refactor" looks great until the spec is vague

This style (build → test → clean up) had excellent change cost (within ~2% of the best)
and was cheaper than TDD. But under a vague spec it scored **0%** on edge cases — worse
than plain test-after.

The reason: the cleanup step rewrote the code and, in the process, **deleted the very
tests that recorded the edge-case decisions**. Clean code, no edge coverage. It's a fine
choice when the spec is clear, but the refactor step is risky when it isn't.

### 6. The cost difference is real

| Coding style | Cost per stage |
|---|---|
| test-after | **$0.19** (cheapest) |
| TDD without refactoring | $0.22 |
| big design up front | $0.24 |
| test-after-refactor | $0.35 |
| TDD with refactoring | $0.44 (most expensive) |

TDD with refactoring costs about **2.3× more** than test-after, because of all the
back-and-forth in the test-first loop. That's the price of its changeability benefit.

---

## What to actually do

| Your situation | Best choice |
|---|---|
| The spec is vague | **Stop and clarify first.** No workflow — not even auto-writing a detailed spec — recovers a decision nobody made. |
| Clear spec, code that will live and change for a long time | **TDD with refactoring** — it produces the most change-friendly code. |
| Clear spec, one-shot or budget-conscious | **test-after** — same quality, ~2.3× cheaper. |
| You want cleaner code without TDD's overhead | **test-after-refactor**, but **only with a clear spec** (under a vague one it loses edge coverage). |
| Throwaway / speed-first | **test-after or TDD without refactoring** — same changeability, lowest cost. |

**The one-sentence version:** Good code habits (especially refactoring) make code easier
to change — but no habit substitutes for asking what the spec left out.

---

*Plain-language summary of [`when-tdd-pays-report.md`](when-tdd-pays-report.md).
All numbers and method details are in the full report.*
