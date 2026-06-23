# Database Test Patterns

Reference file for the `cd-test-architecture` and `test-design-advisor` skills and the `test-smell-review` agent. Tests that touch a real database are the most common source of Erratic Tests, Test Run Wars, and Slow Tests — and the hardest to make safe for a CD pipeline. This file covers how to **isolate**, **tear down**, and **avoid** database state so persistence tests stay independent and repeatable.

Source: Gerard Meszaros, *xUnit Test Patterns* (xunitpatterns.com) — Ch. 13 *Testing with Databases* and Ch. 25 *Database Patterns*. Language- and engine-agnostic.

Core principle: **a database test must leave the world exactly as it found it, and must not collide with any other test or test run.** State that leaks across tests creates order-dependence (Interacting Tests); state shared across concurrent runs creates Test Run Wars. The whole game is isolation + reliable teardown — or removing the database from the test entirely.

---

## First question: does this test need a real database at all?

Most logic that *uses* data does not need to test the *database engine*. Push the decision down:

```
What is actually under test?
├─ Business logic that happens to read/write data
│   └─ Replace persistence with a Fake (in-memory repository / In-Memory Database).
│      Fast, deterministic, pre-merge-gate safe. This is the default. (see test-doubles.md)
│
├─ The mapping/queries themselves (ORM config, SQL, schema constraints)
│   └─ A real database IS the SUT — use the isolation + teardown patterns below.
│
└─ Stored procedures / DB-side logic
    └─ Stored Procedure Test against a real engine, isolated per run.
```

A suite that spins up the whole database to test ordinary domain logic is the **Slow Tests** smell with a side of fragility. Reserve real-DB tests for the cases where the persistence layer itself is the thing being verified.

---

## Isolation: keep test runs from colliding

| Pattern | What it does | Trade-off |
|---------|-------------|-----------|
| **Database Sandbox** | Each developer / CI runner gets its **own** database, so no two runs share rows | The baseline. Without it, concurrent runs cause Test Run Wars |
| → *Dedicated Database Sandbox* | A separate lightweight DB instance per user/runner | Most flexible (schema changes allowed); needs a per-runner instance |
| → *DB Schema per Test Runner* | One engine, a separate **schema** per runner; an Immutable Shared Fixture can live in a common schema | Cheaper; users can't diverge the structure |

A Sandbox separates *runs* from each other; it does **not** make the tests *within* a run independent — that still requires a Fresh Fixture per test plus the teardown below.

---

## Teardown: undo what the test did

Pick the cheapest teardown that fully restores state. Prefer rollback; fall back to truncation.

| Pattern | How it cleans up | Use when | Caveats |
|---------|------------------|----------|---------|
| **Transaction Rollback Teardown** | Run the whole test in a transaction; roll back at the end so nothing commits | A Fresh-Fixture test on an engine with rollback; **fastest** and schema-change-proof | The SUT must **never commit** — it must run inside a transaction owned by a *Humble Transaction Controller* (`testability-patterns.md`). A stray commit silently defeats it |
| **Table Truncation Teardown** | Delete/truncate the tables the test populated | The SUT commits, or rollback isn't usable | Must truncate in FK-safe order; more teardown code to maintain |
| **Delete-by-key / scoped cleanup** | Remove just the rows this test created (often via *Automated Teardown* tracking inserted keys) | Targeted cleanup in a shared schema | Easy to miss a table → leaked state |

Rule of thumb: **Transaction Rollback Teardown** when the design permits it (and design *toward* permitting it via a Humble Transaction Controller); **Table Truncation Teardown** when commits are unavoidable.

---

## Stored Procedure Test

When logic lives in the database (procedures, triggers, functions), it still deserves a test: arrange inputs in tables/parameters, invoke the procedure, verify the returned result set or the resulting table state, then tear down (rollback or truncation). Treat the procedure as the SUT and apply the same isolation. Note that DB-side logic is harder to keep under the pyramid's fast layers — prefer moving non-trivial logic *out* of the database where the team's primary tooling can test it (*Ensure Commensurate Effort*, `test-automation-principles.md`).

---

## CD pipeline placement

- A real database makes a test roughly **an order of magnitude slower** than an in-memory equivalent — Meszaros cites ~50× for round-trips. That cost decides pipeline stage.
- **Pre-merge gate:** Fake/in-memory persistence (deterministic, no external config). This is where the bulk of data-touching tests belong.
- **Later stage:** the narrow band of real-DB tests that verify mapping/schema/procedures, running against a per-runner Sandbox with rollback or truncation teardown.
- A database test that needs a human to seed data or reset state is the **Manual Intervention** smell and cannot gate a pipeline — automate the setup or it doesn't ship. See `cd-test-architecture.md` for the determinism→stage rule this feeds into.

---

## How this connects to the rest of the toolkit

- **`cd-test-architecture.md`** — owns the determinism→pipeline-stage decision; this file supplies the persistence-specific isolation/teardown that makes a DB test gate-eligible.
- **`test-doubles.md`** — the Fake Object (in-memory DB/repository) that lets most data-logic tests avoid a real database entirely.
- **`testability-patterns.md`** — the *Humble Transaction Controller* (a Humble Object) that Transaction Rollback Teardown depends on.
- **`test-smells.md`** — Erratic Test (Test Run War, Interacting Tests), Slow Tests, Manual Intervention: the smells unmanaged database state produces.
- **`test-strategy.md` / `fixture-construction.md`** — Fresh vs. Shared Fixture and Automated Teardown, the general machinery this specializes for databases.
