# The Test Pyramid

Reference file for `test-review`, `test-smell-review`, and the `test-design-advisor` skill. The test pyramid is a heuristic for *where* a given check belongs: many fast, isolated tests at the base; progressively fewer, slower, broader tests toward the top.

Source: Martin Fowler, "The Practical Test Pyramid" (martinfowler.com/articles/practical-test-pyramid.html), building on Mike Cohn's original. Language- and stack-agnostic.

Core principle: **push each check to the lowest layer that can meaningfully verify it.** A bug catchable by a unit test should be caught by a unit test — it's faster, more precise, and more stable there. Reserve higher layers for what genuinely needs integration.

---

## The Layers

| Layer | Scope | Speed | Doubles | What it proves |
|-------|-------|-------|---------|----------------|
| **Unit** | One unit (class/function/module) in isolation | ms | Stub/Fake collaborators | Logic, branches, edge cases of that unit |
| **Integration** | The unit + one real external it talks to (DB, queue, HTTP client, filesystem) | 10s–100s ms | Real adapter, often a test container | The adapter/serialization/wiring actually works |
| **Component / Service** | One deployable service in isolation, internals real, *its* externals stubbed | 100s ms–s | Stub the service's own external deps | The service satisfies its own contract end to end, in-process |
| **Contract** | The agreement between a consumer and a provider | fast | n/a (verifies a pact) | Two services still agree on the interface (see `microservice-testing.md`) |
| **End-to-End** | The whole system through real entry points (UI/API) | s–min | none (real everything) | Critical user journeys work when wired together |

"Unit" can be **solitary** (all collaborators doubled) or **sociable** (real collaborators used, only true boundaries doubled). Both are legitimate; sociable unit tests catch wiring bugs solitary ones miss, at the cost of broader blast radius on failure. Prefer sociable for cohesive collaborators, solitary across architectural boundaries.

---

## Layer-Selection Heuristics

Ask, for each thing you want to verify:

1. **Is it pure logic / a branch / an edge case?** → Unit. Always.
2. **Does it depend on real serialization, SQL, or a third-party client behaving a certain way?** → Integration (test the adapter, not the logic around it).
3. **Does it cross a service boundary you don't own?** → Contract test, not E2E.
4. **Is it a business-critical journey a user actually performs?** → one E2E test. Not every permutation — just the journey.

If a check could live at two layers, choose the **lower** one. Duplicating the same assertion at a higher layer is redundant coverage (a project smell — see `test-smells.md`).

---

## Anti-Patterns

| Anti-pattern | Shape | Symptom | Fix |
|--------------|-------|---------|-----|
| **Ice-cream cone** | Inverted pyramid — mostly E2E/manual, few unit | Slow suite, flaky CI, slow feedback, hard failure triage | Push logic checks down to unit; keep E2E for journeys only |
| **Hourglass** | Many unit + many E2E, no integration middle | Wiring/serialization bugs slip the gap between layers | Add integration tests for adapters and boundaries |
| **Cupcake** | Same scenarios re-tested at every layer | Maintenance multiplied; one behavior change breaks N tests | De-duplicate; each behavior verified at exactly one layer |
| **Testing through the UI for logic** | Driving a browser to check a calculation | Slow, fragile, obscures the real assertion | Unit-test the calculation; UI test only the rendering/journey |

---

## Other shapes (a strategy lens)

The pyramid is the default, but the *right silhouette follows the architecture*. Two shapes are legitimate, not anti-patterns, when the architecture earns them:

| Shape | Silhouette | Fits when | Source |
|-------|-----------|-----------|--------|
| **Pyramid** | wide unit base, narrow E2E top | logic-heavy code with real internal seams | Cohn / Fowler |
| **Testing trophy** | small unit, **fat integration middle**, some E2E, static analysis as the base | thin-logic apps where most risk is in wiring/serialization (typical UI + API glue) | Kent C. Dodds |
| **Diamond** | thin unit, **bulging integration/component**, thin E2E | services that are mostly orchestration/adapters over little domain logic | — |

Same rule still governs: **push each check to the lowest layer that can verify it.** The trophy and diamond are wide in the middle because *that is where the behavior lives* in those architectures — not as a license to skip unit tests for real logic.

### Shape ↔ architecture fit

| If the codebase is… | Expected shape | A different shape signals |
|---------------------|----------------|---------------------------|
| Rich domain / business logic | pyramid | inverted → logic untested at unit level |
| Thin glue over frameworks/APIs | trophy | tall pyramid → unit tests asserting framework behavior (low value) |
| Orchestration / adapter-heavy service | diamond | wide unit base → over-mocked tests proving little |
| Static site / content | flat (a11y + link/build checks) | any tall shape → testing the framework |

Diagnose by comparing the suite's actual shape to the shape its architecture *should* produce. A mismatch — not the silhouette alone — is the finding.

---

## How to use this during review

- A unit-level test doing **real I/O** (DB, network, disk, sleep) is mis-layered → flag as **Slow Tests** smell; move the I/O to an integration test and double the boundary at unit level.
- An **E2E test asserting a single edge case** (e.g., validation of one field) → flag as mis-layered; that's a unit concern.
- A suite that is **all E2E with little/no unit coverage** → flag the ice-cream-cone shape at the suite level.
- Before flagging "wrong level," confirm the *intended* level of the file (path, naming, framework markers). Integration/E2E tests are *supposed* to touch real resources — don't flag them as slow or non-deterministic for doing their job.

## Boundaries

- The pyramid is a heuristic, not a quota. Don't invent a numeric ratio and flag suites for missing it. Flag *shape pathologies* (inverted, gap in the middle, pervasive duplication), not arithmetic.
- Some domains legitimately carry more integration/E2E weight (thin-logic integration glue, data pipelines). Judge by "is this check at the lowest layer that can verify it," not by silhouette alone.
