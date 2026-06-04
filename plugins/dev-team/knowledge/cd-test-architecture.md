# CD Test Architecture

Reference file for the `cd-test-architecture` skill and the `test-design-advisor` skill. Defines a test architecture aligned to a Continuous Delivery pipeline: **fast, deterministic tests, with minimal tooling, that fully validate behavior — including how a component interacts with other services — and run in CI without configuring the rest of the system the component depends on.**

Source vocabulary: MinimumCD Practice Guide — Test Types (beyond.minimumcd.org/docs/testing/test-types/) and Applied Testing Strategies (beyond.minimumcd.org/docs/testing/applied-testing-strategies/). Component-specific patterns are in `component-test-patterns.md`.

Core principle: **a pre-merge gate may contain only deterministic tests.** A test that depends on a system the team doesn't control — or that must be configured to run — is non-deterministic and belongs out of the merge path. The way to keep behavior coverage in the gate anyway is to replace uncontrolled systems with test doubles, and to keep those doubles honest with a separate validation loop.

---

## The Six Test Types

| Type | Verifies | Dependencies | Deterministic? | Pre-merge gate? | Pipeline stage |
|------|----------|--------------|----------------|-----------------|----------------|
| **Static analysis** | Non-running code: security, complexity, best-practice | none | yes | **yes** | Stage 1 |
| **Unit** | A unit of behavior through its public interface (what it does, not how) | isolated (doubles) | yes | **yes** | Stage 1 |
| **Component** | A single component through its public interface, with systems the team doesn't control replaced by doubles | doubles for uncontrolled systems | yes | **yes** | Stage 1 |
| **Contract** | Interface boundaries with external systems, using doubles (a.k.a. narrow integration). Pins the request sent + response shape depended on | doubles; *validated by integration* | yes | **yes** | Stage 1 |
| **Integration** | That the contract's doubles still match the real system. Exercises real external dependencies | real systems | **no** | **never** | Stage 1/2 for team-controlled containers; out-of-band/scheduled for third-party |
| **End-to-end** | Two or more real components up to the full system | real components | **no** | **never** | Post-deploy smoke; never gates the build |

**Unit** has two shapes: *solitary* (all collaborators doubled) and *sociable* (real in-process collaborators, only true boundaries doubled). Both are deterministic and pre-merge.

---

## The Pre-Merge Gate Rule

Pre-merge (the gate that blocks a merge) contains **only**: static analysis, unit, component, and contract tests. These are deterministic and need nothing configured.

Integration and end-to-end tests are non-deterministic by nature (real systems, real network, shared state) and **never gate a merge**. They run:

- **Stage 1/2 (still in CI)** when the dependency is a *team-controlled* container (testcontainers/WireMock) the build spins up itself.
- **Out-of-band / scheduled** when the dependency is a *third-party API, managed broker, or another team's service*.
- **Post-deploy** for end-to-end smoke of critical journeys against real backends — blocking rollout, not the build.

If a "unit test" needs a database URL, a broker, a downstream service, or environment secrets to run, it is mis-typed — it's an integration test wearing a unit test's name. Re-type it or convert it to a component test with doubles.

---

## How Component Tests Run Without Configuring Dependencies

The component test is the workhorse of a CD gate. The pattern, consistent across every component type:

1. **Assemble the real component** — the actual handlers, domain logic, and orchestration — in-process.
2. **Replace only what the team doesn't control** with in-memory doubles: the database (in-memory repository), the message broker (in-memory bus), downstream services (stubbed adapter), the clock (injected fixed clock), the scheduler.
3. **Drive it through its public interface** — HTTP handlers, the message handler, the job entrypoint, the UI via a real browser with the network stubbed.
4. **Assert on observable outcomes** — status, persisted state, emitted event, rendered output — never on internal call sequences or private methods.

This yields tests that are fast (no I/O, no network), deterministic (no real systems, controlled clock), and need zero configuration of the surrounding system — while still validating real behavior end to end *within the component boundary*, including how it would interact with its collaborators (verified by contract, made real by integration).

---

## The Adapter Rule (own your boundaries)

Wrap every third-party client (SDK, HTTP client, broker client, DB driver) in **a thin adapter the team owns**, then double the *adapter* in component tests — never mock the third-party SDK directly. The adapter is the seam:

- **Component tests** double the adapter → fast, deterministic, no real dependency.
- **Adapter integration tests** exercise the real adapter against a real container → assert the *adapter's* correctness (it speaks the protocol, builds the right request), not the dependency's behavior.

This keeps the mock surface small, stable, and owned, and localizes every "the real thing changed" failure to one place.

---

## Double Validation (keeping doubles honest)

A double that drifts from reality gives false confidence — the central risk of double-based isolation. Keeping a double honest has two independent jobs: **detect** when reality diverges, and **survive** the divergence when it happens.

### Do not depend on provider cooperation

Consumer-driven contract verification — where the *provider* runs your contract in *their* pipeline and is blocked from deploying a breaking change — only works when teams collaborate closely and use tooling that enforces it. **Assume you do not have that.** Design the strategy for the realistic case:

- The provider can break the contract **without versioning**, at any time, with no notice.
- Their production contract is **assumed broken until proven otherwise** — and you typically discover the break during your *next unrelated deploy*, which then wrongly implicates your change and burns an incident investigating the wrong thing.

So provider-side verification is a *nice-to-have if the provider offers it* — never the mechanism you rely on.

### The defense you own

1. **Contract test** (pre-merge) pins the request the consumer sends and the response shape it depends on, against the adapter double. Blocks the build. This keeps *your* side stable and documents exactly what you assume of the provider.
2. **Scheduled provider-contract verification in a test environment** — *you* run your pinned contract against the provider's real (non-prod) endpoint **on a schedule, out-of-band**, decoupled from your deploy cadence. This is the primary defense: it detects a provider break **when it happens**, not when you next ship, so the break is attributed to the provider and not to your undelivered changes. Owned and run by your team; requires no provider cooperation.
3. **Adapter integration test** (Stage 1/2) runs the adapter against a real container of the production engine/broker (matching version + extensions) to confirm the double's protocol assumptions hold for dependencies you control.
4. **Resilience verified by component tests** (pre-merge) — because you assume the provider *will* break, the consumer must be tested to **survive** it: timeouts enforce, retries/backoff/circuit-breaker behave, malformed or drifted responses are handled per Postel's Law, and the caller gets a documented response with no partial state. Detection (step 2) tells you it broke; resilience keeps you up until it's fixed.

Doubles without steps 2 and 4 are a smell (see `microservice-testing.md` → "Stubs that lie", `test-smells.md` → behavior smells). The classic failure is a hand-written double that the team *assumes* still matches a provider nobody is checking.

---

## Determinism Techniques (minimal tooling)

- **Inject the clock.** Replace system time with a fixed clock in every time-dependent test (`Clock.fixed(...)`). Keep exactly one out-of-band real-clock check to confirm production wiring (catches "tests use UTC, prod uses container local time").
- **Inject randomness.** Same discipline for RNG and ID generation.
- **No sleeps.** Never `sleep` to await; drive time and async deterministically.
- **Real browser, stubbed network (UI).** Run UI component tests in a real engine (Chromium/Firefox/WebKit) with the backend stubbed at the network layer — not an in-memory DOM shim, which trades accuracy for speed and produces false positives on layout/timing.
- **In-memory doubles over heavyweight test infra** for the gate. Reserve containers for adapter integration, off the merge path.

---

## Terminology Reconciliation (read this if you also use the Fowler files)

This file uses **MinimumCD vocabulary**, which differs from the Fowler-based `test-pyramid.md` and `microservice-testing.md`:

| Term | MinimumCD (this file) | Fowler (`test-pyramid.md`) |
|------|----------------------|----------------------------|
| **Component test** | Whole component through its public interface, uncontrolled systems doubled, **deterministic, pre-merge** | "Component / Service" — similar intent |
| **Contract test** | Doubles that pin the boundary, **pre-merge**, validated by integration | Consumer-driven contract — same idea |
| **Integration test** | Exercises real deps **specifically to validate the doubles**, non-deterministic, **post-merge only** | Broader: any test of a unit + one real external |
| **Pre-merge gate** | Determinism is the gating criterion | Implicit in "fast tests at the base" |

When advising for a CD pipeline, **prefer this file's framing** — the determinism→pre-merge axis is the organizing principle. Use the Fowler files for the general layering heuristic and the doubles taxonomy (`test-doubles.md`).

## Boundaries

- "Minimal tooling" means prefer in-memory doubles + a real browser + testcontainers for adapter checks — not a sprawl of test frameworks. Don't recommend heavyweight orchestration (full docker-compose of the system) for the gate; that's exactly the configured-dependency dependency this architecture removes.
- These are starting points, not mandates. Real components have details these layers don't capture; drop items that don't apply and add what a component clearly needs.
- This file defines the *architecture*. Per-component specifics (what to double, which failure modes) are in `component-test-patterns.md`.
