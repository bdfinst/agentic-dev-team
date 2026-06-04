# Test Strategy

Reference file for `test-review`, `test-smell-review`, and the `test-design-advisor` skill. Where `test-smells.md` catalogues what to *avoid* and `test-doubles.md` covers *which collaborator stand-in* to use, this file covers the **up-front strategic choices** made before and while building a test: how the fixture is organized, how the test is driven, and how it reaches the system under test (SUT).

Source taxonomy: Gerard Meszaros, *xUnit Test Patterns* (xunitpatterns.com), "Test Strategy" patterns. Language- and framework-agnostic — described by role, not by any tool's API.

Core principle: **default to the simplest, most isolated strategy, and only trade isolation away under measured pressure.** Minimal + Fresh fixtures, scripted tests, and front-door interaction are the defaults; every step away from them buys speed or reach at the cost of clarity or coupling, and must be justified.

---

## 1. Test Fixture Strategy

The fixture is everything the test needs in place before it acts. Two independent decisions:

**A. Design — how much fixture?**

| Strategy | What it is | Use when | Cost / risk |
|---|---|---|---|
| **Minimal Fixture** | Build only what *this* test uses | **Default.** Always start here | — (this is the safe choice) |
| **Standard Fixture** | One fixture *design* reused across many tests (a "big design up front" for the suite) | Many tests genuinely share the same shape and a common design reduces duplication | Drifts into the **General Fixture** smell if it builds more than each test needs (see `test-smells.md`) |

**B. Lifecycle — how long does the instance live?** (orthogonal to A)

| Strategy | What it is | Use when | Cost / risk |
|---|---|---|---|
| **Fresh Fixture** | A new instance built and torn down per test — every test starts from a clean slate | **Default.** Guarantees isolation | Slow if setup is heavy (esp. persistent/DB fixtures) |
| **Immutable Shared Fixture** | One instance reused across tests but never mutated (read-only) | Fresh is too slow *and* tests only read the fixture | Requires discipline that nothing writes to it |
| **Shared Fixture** | One mutable instance reused across many tests / runs | Last resort, when even an immutable shared fixture won't do | Inter-test coupling, order-dependence, **Interacting Tests / Unrepeatable Test / Test Run War** (see `test-smells.md`) |

**Decision flow:** Minimal + Fresh → if too slow, make it an **Immutable Shared Fixture** → only then a mutable **Shared Fixture**, and if shared+persistent, isolate it (per-test DB sandbox / partition scheme) so runs can't collide. Standard vs ad-hoc is a separate axis: a Shared Fixture is always Standard, but a Standard Fixture can still be built Fresh per test.

---

## 2. Test Automation Strategy

How the test is written and driven.

| Strategy | What it is | Use when | Cost / risk |
|---|---|---|---|
| **Scripted Test** | Test programs written by hand (the test code you write in any xUnit) | **Default**, and the only option that can *drive* development (TDD) — there's nothing to record before the code exists | Needs programming skill; not for non-technical authors |
| **Data-Driven Test** | A common interpreter holds the logic; cases live as rows in an external data table (one line per case) | Many cases vary only by input/expected data; lets non-programmers add cases (e.g. Fit/Fitnesse) | Interpreter is itself code to maintain; failures can be opaque; easy to over-build |
| **Recorded Test** | Capture interactions with a running SUT (usually through the UI) and replay them | Regression-testing a **finished, stable** app where little will change | Brittle to UI/behavior change; can't drive development; high re-record cost |
| **Test Automation Framework** | The harness that discovers, runs, verifies, and reports tests; you supply only test-specific logic | You **use** one (xUnit, etc.) — rarely build one | Building your own is almost always wasted effort |

Rule of thumb: **scripted by default; data-driven when the variation is purely data; recorded only for regression on something already done.**

---

## 3. SUT Interaction Strategy

How the test reaches the system under test.

| Strategy | What it is | Use when | Cost / risk |
|---|---|---|---|
| **Layer Test** | Treat each layer of a layered architecture as its own SUT; test layer *n* with tests standing in for *n+1* and (optionally) a Test Double for *n-1* | The system is layered and you want precise per-layer coverage | Requires real layer boundaries (see `hexagonal-architecture`); misses cross-layer integration bugs unless complemented by broader tests |
| **Back Door Manipulation** | Set up pre-state or verify post-state by bypassing the SUT's public API — direct DB/file/registry access | Front-door setup/verification is impractical, slow, or so verbose it obscures the test's intent | Couples the test to the SUT's internal state representation; can mask real integration defects — use sparingly and deliberately |

**Front-door first.** Prefer driving and checking the SUT through its real API; reach for a back door only when the front door makes the test unclear or infeasible.

> **Reconciling with the "Test Logic in Production" smell.** `test-smell-review` flags back doors *baked into shipped code* (`if (testMode)`, test-only endpoints) — that is always a smell. **Back Door Manipulation is different:** it is the *test* reaching around the API to touch state the SUT owns, with no change to production code. The first is production code that knows it's being tested; the second is a test that knows the SUT's internals. The former is banned; the latter is a costed trade-off. Don't conflate them in review.

---

## How this connects to the rest of the toolkit

- **`test-doubles.md`** — once Layer Test or Back Door Manipulation needs a collaborator stand-in, choose the double there.
- **`test-smells.md`** — the failure modes these strategies guard against (General Fixture, Interacting Tests, Mystery Guest, Test Logic in Production).
- **`test-pyramid.md`** — *where* a check belongs (granularity); this file is *how* the test at that layer is built.
- **`testability-patterns.md`** — the seams (dependency injection, etc.) that make Fresh Fixtures and front-door interaction possible without back doors.
- **`cd-test-architecture.md` / `microservice-testing.md`** — applying fixture and interaction strategy in a CD / distributed context.
