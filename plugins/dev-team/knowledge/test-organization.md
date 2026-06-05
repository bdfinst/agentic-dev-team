# Test Organization

Reference file for `test-review`, `test-smell-review`, and the `test-design-advisor` skill. This file covers how a single test and a whole suite are *structured* — the Four-Phase Test that every test follows, how test classes are grouped, how shared logic is reused, and how the runner finds tests.

Source: Gerard Meszaros, *xUnit Test Patterns* (xunitpatterns.com) — Test Organization patterns + XUnit Basics. Language- and framework-agnostic — described by role, not any runner's API.

Core principle: **make the structure of every test obvious** — its four phases, its place in a cohesive class, and its name — so the suite reads as documentation.

---

## The Four-Phase Test (the anchor)

Every test follows four phases, visibly separated:

1. **Setup** — establish the fixture (→ `fixture-construction.md`).
2. **Exercise** — invoke the SUT.
3. **Verify** — assert the outcome (→ `result-verification.md`).
4. **Teardown** — release what Setup created (→ `fixture-construction.md`).

When setup, exercise, and assertions are interleaved with no visible phases, that is the **Obscure Test** smell — restructure into four phases first.

---

## Testcase Class grouping

| Grouping | One class per… | Use when | Trade-off |
|---|---|---|---|
| **Testcase Class per Class** | production class | default, simple SUTs | can bloat as the SUT grows behaviors |
| **Testcase Class per Feature** | feature/behavior across classes | a feature spans several production classes | needs a clear feature boundary |
| **Testcase Class per Fixture** | shared setup | one class's methods need *different* setups | more classes, but each has one cohesive fixture (kills General Fixture) |

Split into **Testcase Class per Fixture** when a single class's methods diverge in what they set up.

---

## Sharing logic: composition over inheritance

| Mechanism | What it is | Use when |
|---|---|---|
| **Test Utility Method / Test Helper** | Shared arrange/assert logic as called methods (composition) | **Default** for any shared logic — explicit, low-coupling |
| **Testcase Superclass** | A base test class supplying shared setup/utilities via inheritance | Only for genuinely *universal* setup across many classes; couples every subclass to it |

Prefer a Test Utility Method / Helper; escalate to a Testcase Superclass only for truly universal setup, and note its coupling cost.

---

## Parameterized Test

When several test methods differ only by input/expected **data**, collapse them into a **Parameterized Test** — one test logic over many data rows. This is the in-code counterpart of the **Data-Driven Test** automation strategy in `test-strategy.md`; use it when the variation is purely data, not when cases differ in logic.

---

## Test Discovery / Enumeration / Selection + naming

The runner finds tests by **Test Discovery** (convention/annotation), builds a **Test Enumeration**, and runs a selected subset. Two consequences for design:

- Give each test an **intent-revealing name** stating the scenario and expected outcome — the name is the first line of documentation a failure shows.
- Keep tests selectable (tags/categories) so fast and slow suites can be run separately.

**Decision flow:** make the four phases visible → group classes per fixture when setups diverge → share via a Test Utility Method, escalating to a Testcase Superclass only for universal setup → collapse data-only duplication into a Parameterized Test → name every test for its scenario.

---

## How this connects to the rest of the toolkit

- **`fixture-construction.md`** — the Setup/Teardown phases.
- **`result-verification.md`** — the Verify phase.
- **`test-strategy.md`** — Parameterized Test ↔ Data-Driven Test.
- **`test-smells.md`** — the smells these fix: Obscure Test, Test Code Duplication, High Test Maintenance Cost.
- **`test-refactoring.md`** — the moves that get an existing suite here: Extract Testcase Class per Fixture, Extract Test Utility Method, Introduce Parameterized Test, Split Test.
