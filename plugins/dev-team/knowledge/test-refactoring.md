# Test Refactoring & Automation Principles

Reference file for `test-review`, `test-smell-review`, and the `test-design-advisor` skill. The capstone of the testing-knowledge set: the **goals & principles** define what a good automated test *is* (the criteria); the **refactoring catalog** lists the behavior-preserving moves that get an existing test there. Together they connect a named smell (`test-smells.md`) to the target pattern in the sibling files and back.

Source: Gerard Meszaros, *xUnit Test Patterns* (xunitpatterns.com) — Goals of Test Automation, Principles of Test Automation, and the Test Refactorings catalog. Language- and framework-agnostic — described by role, not any library's API.

---

## 1. Goals & Principles (the criteria a refactoring moves toward)

**Goals — a good automated test is:**

- **Documentation / specification** — reads as an example of how the SUT is meant to behave.
- **Self-checking** — passes or fails on its own; no human reads output to judge it.
- **Repeatable** — same result every run, any order, any machine.
- **Robust** — breaks only when the behavior it checks changes (not on unrelated edits).
- **Isolated / independent** — does not depend on other tests or leak state to them.
- **Economical** — fast, and cheap to write and maintain.

**Principles — how to get there:**

- Write tests first (drive the design); design for testability.
- Communicate intent (intent-revealing names, Custom Assertions).
- Verify **one condition per test**; minimize test overlap.
- Keep tests **independent**; keep **no logic in tests** (no conditionals/loops around assertions).

A test that violates a goal has a smell; the refactoring below moves it back toward the goal.

---

## 2. Test Refactoring catalog (the behavior-preserving moves)

Each move removes a named smell (`test-smells.md`) and targets a pattern in a sibling file:

| Refactoring | Removes smell | Toward (target file) |
|---|---|---|
| **Inline Mystery Guest** → build data locally via a Creation Method / Fresh Fixture | Mystery Guest | `fixture-construction.md` |
| **Replace General Fixture with Minimal Fixture** | General Fixture, Irrelevant Information | `fixture-construction.md` |
| **Extract Creation Method / Introduce Test Data Builder** | Test Code Duplication (setup) | `fixture-construction.md` |
| **Replace Inline Setup with Implicit / Delegated Setup** | Test Code Duplication (setup) | `fixture-construction.md` |
| **Introduce Expected Object** | Assertion Roulette | `result-verification.md` |
| **Extract Custom Assertion / Verification Method** | Test Code Duplication (verify), poor diagnostics | `result-verification.md` |
| **Add Guard Assertion** | misleading/cryptic failure | `result-verification.md` |
| **Split Test** (one logical condition per test) | Eager Test | `test-organization.md` |
| **Extract Testcase Class per Fixture** | General Fixture, Obscure Test | `test-organization.md` |
| **Extract Test Utility Method / Testcase Superclass** | Test Code Duplication, High Test Maintenance Cost | `test-organization.md` |
| **Introduce Parameterized Test** | data-only duplication | `test-organization.md` |

---

## Decision flow

1. Identify the smell (`test-smells.md`).
2. Name the violated goal/principle (self-checking? isolated? one condition? intent-revealing?).
3. Pick the refactoring above that moves the test toward it.
4. Apply **under green** — and **characterization-first**: if the test (or the code it covers) lacks coverage of current behavior, pin that behavior before any move (`testability-patterns.md`, `legacy-code`).

These are **test-side** refactorings. When the blocker is *production* code that can't be tested at all, use the production seams in `testability-patterns.md` instead — never a test workaround (reflection, `InternalsVisibleTo`, mocking concretes).

---

## How this connects to the rest of the toolkit

- **`test-smells.md`** — the smells each refactoring removes.
- **`fixture-construction.md`** / **`result-verification.md`** / **`test-organization.md`** — the target patterns the moves head toward.
- **`test-strategy.md`** — the lifecycle/automation choices the refactored test should land on.
- **`testability-patterns.md`** / **`legacy-code`** — production seams + characterization-first when the target is untested.
