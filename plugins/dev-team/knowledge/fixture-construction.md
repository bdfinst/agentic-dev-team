# Fixture Construction

Reference file for `test-review`, `test-smell-review`, and the `test-design-advisor` skill. Where `test-strategy.md` decides *which* fixture (lifecycle Fresh/Shared, design Minimal/Standard), this file covers *how* the fixture is built and disposed — the construction mechanics that realize that strategy and fix fixture smells at the root.

Source: Gerard Meszaros, *xUnit Test Patterns* (xunitpatterns.com) — Fixture Setup + Fixture Teardown pattern families. Language- and framework-agnostic — described by role, not any library's API.

Core principle: **build only what this test needs, through intent-revealing construction, and release everything the test created.** Hide irrelevant detail; surface what matters to the behavior under test.

---

## 1. Construction patterns (how the fixture object is built)

| Pattern | What it is | Use when | Cost / risk |
|---|---|---|---|
| **Creation Method** | An intent-revealing factory that builds *and returns* the fixture (`anOverdueAccount()`), hiding irrelevant constructor detail | **Default.** Removes Irrelevant Information and Test Code Duplication | — (the safe first move) |
| **Test Data Builder** | A fluent builder with sensible defaults; each test overrides only the attribute that matters (`anAccount().overdrawn().build()`) | Objects with many attributes, where tests vary one or two | Slightly more code than a Creation Method; worth it past a few variations |
| **Object Mother** | A library of *named canonical* fixtures shared across tests (`Customers.goldTier()`) | A small set of genuinely shared, well-understood standard cases | Tends to grow into a **General Fixture** — each test gets more than it needs; keep it minimal |

**Decision:** Creation Method by default → Test Data Builder when attributes vary per test → Object Mother only for a few genuinely canonical cases. Prefer building through the SUT's public API; if the fixture cannot be constructed that way, that is a **production-code** problem — introduce a seam per `testability-patterns.md`, never reflection or `InternalsVisibleTo`.

---

## 2. Setup location (where construction runs)

| Location | What it is | Trade-off vs Fresh Fixture isolation |
|---|---|---|
| **In-line Setup** | Each test builds its own fixture in the test body | Maximum clarity & isolation; duplication if many tests share shape → extract a Creation Method |
| **Delegated Setup** | Tests call shared Creation Methods, but from the test body | Removes duplication while keeping each test's setup explicit — usually the sweet spot |
| **Implicit Setup** | A per-test hook (`setUp`/`beforeEach`) builds the fixture for every test in the class | Concise, but can drift into **General Fixture**/**Mystery Guest** if it builds more than some tests use |
| **Lazy Setup** | The fixture is created on first use and memoized | Useful for an expensive read-only fixture; risks shared mutable state if not truly read-only |
| **SuiteFixture Setup** | One fixture built once per *suite* of classes | Last resort for very expensive setup; couples tests across classes — pairs with an Immutable Shared Fixture only |

Keep setup **Fresh + Minimal** by default (`test-strategy.md`); each step toward Implicit/Lazy/SuiteFixture trades isolation for speed and must be justified.

---

## 3. Teardown (releasing what the test created)

| Pattern | What it is | Use when |
|---|---|---|
| **In-line Teardown** | The test releases its own resources at the end | Few resources, simple lifetimes |
| **Implicit Teardown** | A per-test hook (`tearDown`/`afterEach`) releases the fixture | Several tests share the same cleanup shape |
| **Automated Teardown** | The fixture layer *registers* everything created and releases it automatically after each test | **Persistent fixtures** (DB rows, files, queues) — prevents resource leakage / **Erratic Test** without per-test cleanup code |

For any fixture that touches persistent state, recommend **Automated Teardown** (or equivalent) so a failing test can't leak state into the next — the root fix for the resource-leakage form of the Erratic Test smell.

---

## How this connects to the rest of the toolkit

- **`test-strategy.md`** — *which* fixture (lifecycle/design); this file is *how* it's constructed.
- **`test-smells.md`** — the smells these fix: Mystery Guest & General Fixture & Irrelevant Information & Test Code Duplication (construction), resource-leakage Erratic Test (teardown).
- **`testability-patterns.md`** — the production seams (DI, interface extraction) that let a built fixture be injected without back doors.
- **`test-doubles.md`** — a Fake (in-memory repo/DB) is itself a constructed fixture; choose the double there.
- **`test-organization.md`** — Setup and Teardown are the first and last of the Four-Phase Test.
- **`test-refactoring.md`** — the behavior-preserving moves (Extract Creation Method, Introduce Test Data Builder, Replace General Fixture with Minimal Fixture) that get an existing test here.
