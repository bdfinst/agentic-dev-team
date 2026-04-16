# Contract Testing Pattern

Contract tests verify interface boundaries with external systems using test doubles. They validate that boundary layer code (HTTP clients, database query layers, message producers) correctly handles expected request/response shapes, field names, types, and status codes.

Contract tests validate **interface structure, not business behavior**. They answer "does my code correctly interact with the interface I expect?" — not "is the logic correct?"

Source: [Beyond Minimum CD — Contract Tests](https://beyond.minimumcd.org/docs/testing/contract/index.html.md)

## Two-Layer Validation

Test doubles and integration tests form a validation loop:

1. **Contract tests (every commit)**: Use test doubles to run deterministically. Fast, no network, no database. Block the build on failure.
2. **Integration tests (post-deploy or periodic)**: Run against live dependencies to validate that test doubles still match real behavior. When a double drifts from reality, the integration test catches it.

The doubles are first-class citizens, not a compromise. They are trustworthy *because* integration tests validate them.

## When to Use Doubles vs Real Dependencies

| Dependency type | Main test flow | Validation |
|----------------|---------------|------------|
| External service (API, third-party) | Test double | Integration test against real service |
| Database | Test double (repository interface) | Integration test against real database |
| Internal module (same codebase) | Real code | N/A — no contract boundary |
| File system, clock, randomness | Injected/stubbed | N/A — determinism concern |

**Key rule**: Use test doubles at *architectural boundaries* (ports in hexagonal architecture). Use real code for everything inside the boundary.

## Consumer vs Provider

**Consumer side**: Your code depends on an external API. Assert only on the subset you actually consume. Follow Postel's Law — be conservative in what you send, liberal in what you accept. Never assert on fields your code doesn't read.

**Provider side**: Your API is consumed by others. Run consumer contract expectations against your real implementation to catch breaking changes before deployment.

## Anti-Patterns

- Asserting on business logic in contract tests (belongs in component/unit tests)
- Over-specifying by asserting on unused fields
- Testing specific data values instead of types and structures
- Hitting live systems in the deterministic pipeline (breaks build reliability)
- Skipping the integration tests that validate the doubles (doubles drift silently)
- Treating doubles as a compromise instead of the preferred approach
