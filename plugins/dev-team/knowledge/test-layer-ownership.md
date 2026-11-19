# Test Layer Ownership

Reference file for `system-test-design`, `cd-test-architecture`, and `test-design-advisor`. Vocabulary: MinimumCD test types (<https://beyond.minimumcd.org/docs/foundations/testing-fundamentals/test-types/>, glossary at <https://beyond.minimumcd.org/docs/foundations/testing-fundamentals/glossary/>). The gate that decides E2E stays canonical in `cd-test-architecture.md`; this file does not restate it.

## In band and out of band

- **In band:** deterministic, runs in the pipeline, and blocks a build or deploy on failure. Doubles replace dependencies across boundaries. A real engine that the team controls and isolates per test (for example a per-test container database) is acceptable.
- **Out of band:** non-deterministic, scheduled or post-deploy, runs against real systems, and never blocks a commit or merge. It confirms that in-band doubles still match reality.

Anything that blocks a deploy must be deterministic and team-controlled. An in-band test that calls a shared or external service is a finding.

## What each type owns

The per-type "Owns" column lives in *The Six Test Types* table in `cd-test-architecture.md`. Summary:

- **Static analysis:** type errors, security vulnerabilities, complexity, best-practice violations.
- **Unit:** logic (calculations, branching, validation, mapping). Solitary (all collaborators doubled) or sociable (real in-process collaborators). All external I/O is doubled.
- **Component:** seams between layers inside one component: persistence, serialization, status mapping, auth middleware, error handling, retries against stubbed failures, graceful degradation, message handling. Out-of-process dependencies are replaced by wire-level stubs, virtual services, in-memory equivalents, or a per-test isolated instance of a team-controlled engine such as a database or broker. Downstream services are always doubled.
- **Contract:** the interface boundary: request payloads, query parameters, headers, response schemas, status codes, message formats. The consumer side runs against the consumer code. The provider side runs against every published consumer expectation.
- **Integration:** that doubles still match reality: driver and dialect mismatches, schema serialization, connection configuration, transport errors. Out of band, always, whatever instance it runs against (see `cd-test-architecture.md`, The Pre-Merge Gate Rule).
- **E2E:** critical business flows and entangled workflows that cannot be verified another way. Acceptance tests, if deterministic, run in an ephemeral environment the run provisions and removes. They run post-deploy or scheduled, never pre-merge and never as a build gate (`cd-test-architecture.md`, Placement options).

Smoke tests and synthetic monitoring run after deploy. Record them as E2E placement, not as owners of behavior.

## Ownership decision

For each behavior, ask in order. The first "yes" sets the owner.

1. Can static analysis detect the failure?
2. Can a unit test with no I/O detect it?
3. Can a component test with out-of-process dependencies doubled detect it?
4. Is the failure a mismatch between what a consumer sends or expects and what a provider accepts or returns, *through an explicit interface*? Then contract. A shared table, shared domain type, or lockstep deployment is not an explicit interface; see `entangled-workflows.md`.
5. Is the failure a difference between a double and the real dependency? Then integration.
6. Otherwise E2E, only when the gate in `cd-test-architecture.md` holds. If it does not hold, record the risk as accepted or recommend synthetic monitoring.

Classify a test by what is real and what is doubled, never by folder or project name.

## Do not test consumed services

Test how the system parses the fields it needs. Test how it responds when the dependency is slow, unavailable, or wrong. Do not test the dependency's own behavior.

## Duplication checks

- The same assertion in two types: keep it in the owner and remove it elsewhere. A broader test may pass through the behavior without asserting it.
- An E2E used as a regression net for edge cases, error handling, or validation belongs lower (inverted pyramid).
- Component tests assert the seam, not each input edge case of a unit rule.
- Integration tests verify the boundary. Move business permutations to unit or component tests.
- Several E2Es for one flow that differ only in data: keep one.
- UI-tested behavior that a lower layer can test moves lower.

## Removal rule

Recommend removing an E2E only after replacement component tests pass and their doubles are validated by a contract test and an out-of-band integration test. Until then, mark it for removal after replacement. Never keep both.

## Antipatterns

Report each with its fix.

| Antipattern | Fix |
| --- | --- |
| Doubles without validating tests | Add a contract test and an out-of-band integration test per double |
| Mocking what you don't own (third-party SDK, ORM, HTTP client) | Wrap it in a team-owned gateway and double the gateway |
| Over-mocking (entities, DTOs, simple in-process objects) | Sociable unit test with real collaborators |
| Tests that mirror the implementation (sequence of internal calls) | Assert the outcome through the public interface |
| Testing private methods or through reflection | Test behavior through the public interface |
| Complex mock setup | Design finding: too many dependencies |
| Sleeping in tests | Bounded, condition-driven polling or a fake clock |
| Shared mutable state (shared databases, caches, singletons) | Isolate per test; reset stubs and stores |
| Shared remote environments in in-band tests | Ephemeral infrastructure per run |
| Flaky tests rerun until they pass, or skipped or muted | Quarantine, then fix or delete |
| E2E UI selectors on CSS classes or XPath | Accessibility role or stable data attribute |
