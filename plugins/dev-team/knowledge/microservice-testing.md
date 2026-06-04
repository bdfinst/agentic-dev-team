# Microservice Testing Strategy

Reference file for `test-smell-review` and the `test-design-advisor` skill. Distributed systems add failure modes a single-process pyramid doesn't cover: the network between services, and the *agreement* between a service and its consumers. This file covers the layers and the contract-testing discipline that keep independently-deployable services from breaking each other.

Source: Martin Fowler / Toby Clemson, "Testing Strategies in a Microservice Architecture" (martinfowler.com/articles/microservice-testing/). Complements `test-pyramid.md`.

> For CD-pipeline framing — the determinism→pre-merge-gate rule, running CI without configuring dependencies, and per-component (UI/service/batch) patterns — see `cd-test-architecture.md` and `component-test-patterns.md`. Note those use MinimumCD vocabulary, where "integration test" specifically means *validating that contract doubles still match reality* (post-merge), which is narrower than this file's usage.

Core principle: **independent deployability requires that no service can be broken by another service's change without a test catching it first.** End-to-end tests are too slow and flaky to be that safety net at scale. Contract tests are — but only when paired with *scheduled verification of those contracts against the real provider* (because you cannot depend on the provider to honor or verify a contract; see the reality check below).

---

## The Layers (per service)

| Layer | Scope | What it verifies | Doubles |
|-------|-------|------------------|---------|
| **Unit** | A single class/function | Internal logic, branches, edge cases | Collaborators doubled |
| **Integration** | A module + one external it owns | The adapter works against a real DB/broker/HTTP peer (test container) | Real external, isolated instance |
| **Component** | One whole service, in isolation | The service meets *its own* API contract end to end, internals real | The service's downstream deps stubbed (in-process or network-level) |
| **Contract** | The consumer↔provider agreement | Both sides still agree on request/response shape & semantics | A pact, verified independently on each side |
| **End-to-end** | Several real services together | A critical cross-service journey works | None — real deployments |

The shape is the same pyramid: lots of unit/integration, a layer of component tests per service, a thin layer of E2E for journeys. The new and load-bearing layer is **Contract**.

---

## Consumer-Driven Contracts (CDC)

The mechanism that lets services deploy independently:

1. The **consumer** writes tests describing exactly the requests it makes and the responses it depends on → this produces a **contract** (a "pact").
2. The contract is shared with the **provider** (a broker, a repo, an artifact).
3. The **provider** runs the contract against itself in *its* CI. If a provider change would break that consumer, the provider's build goes red — before deploy, without the consumer present.
4. Each side tests against the contract in **isolation**: the consumer stubs the provider per the contract; the provider replays the contract against the real implementation.

Why this beats E2E for integration safety:

- Fast and deterministic — no shared environment, no orchestrating N services.
- Failure points at the exact broken expectation, not "something in the journey failed."
- The provider learns it broke a consumer **at build time**, which is what makes independent deploys safe.

> **Reality check — don't depend on step 3.** The full CDC loop above only works when teams collaborate closely *and* use tooling that enforces provider-side verification. For any provider you don't control, **assume that doesn't exist**: assume the provider can break the contract without versioning and that you won't discover it until an incident — usually during your next unrelated deploy, which then takes the blame. The defense you actually own is to run *your* pinned contract against the provider's real endpoint **in a test environment on a schedule, out-of-band**, so a break is detected when it happens and attributed to the provider, not to your undelivered changes. And because you assume the provider *will* break, test that your consumer **survives** it (timeouts, retries, circuit breaker, drifted-response handling). Provider-side verification is a bonus when available, never the mechanism you rely on. See `cd-test-architecture.md` → Double Validation for the CD-pipeline formulation.

---

## What to test where (microservice heuristics)

- **Business logic** → unit, in the owning service. Never via another service.
- **Serialization / DB mapping / broker plumbing** → integration tests with a real instance (test container), not mocks of the driver.
- **"Does my service honor its own API?"** → component test, internals real, downstreams stubbed.
- **"Do I and the service I call still agree?"** → a contract test you own (pins what you send/expect), plus **scheduled verification of it against the provider's real test endpoint**. Provider-side verification too, if available. This replaces most cross-service E2E.
- **"Does this critical journey work end to end?"** → a *small number* of E2E tests for the highest-value journeys only.

---

## Smells specific to distributed testing (flag these)

| Smell | Signal | Fix |
|-------|--------|-----|
| **E2E as the integration net** | Cross-service correctness relies on a large E2E suite; no contract tests | Introduce contract tests + scheduled provider verification; shrink E2E to journeys |
| **Unmonitored provider contract** | Consumer stubs a provider's response, but nobody runs that contract against the real provider on a schedule | Run *your* contract against the provider's real test endpoint on a schedule, out-of-band — don't wait for your next deploy (or the provider's cooperation) to discover a break |
| **Consumer can't survive a break** | Consumer assumes the provider's contract holds; no timeout/retry/circuit-breaker/drifted-response tests | Test that the consumer degrades gracefully — assume the provider *will* break without versioning |
| **Stubs that lie** | Hand-written stubs of a downstream that aren't derived from / checked against the real contract | Pin the stub with a contract test; verify it against the real provider on a schedule |
| **Shared integration environment for correctness** | Tests pass/fail based on the state of a shared staging system | Isolate: component tests with stubbed downstreams + contract tests |
| **Cross-service unit test** | A "unit" test spins up or calls a second real service to check this service's logic | Double the boundary; move true cross-service checks to contract/E2E |

## Boundaries

- Not every codebase is microservices. For a monolith or library, `test-pyramid.md` is sufficient — apply this file only when there are independently-deployable services with network boundaries between them.
- Contract testing is the recommendation for service↔service agreements; don't flag the *absence* of E2E tests as a defect when contracts cover the integration. The point is independent deployability, achieved by whichever combination provides it.
- A small, curated E2E suite is healthy. Flag E2E *over-reliance* (it's the integration safety net), not E2E existence.
