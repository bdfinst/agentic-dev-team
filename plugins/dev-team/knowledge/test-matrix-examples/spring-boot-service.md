# Worked example — Spring Boot REST service

Few-shot template for `test-design-advisor`. Adapt the rows. Feature: **a service exposes `POST /transfers`, applies a business rule (no overdraft), persists, and publishes a `TransferCompleted` event**. Rich domain logic → **pyramid** shape (`test-pyramid.md`).

## Pyramid placement (advisor output shape)

| Behavior | Layer | Gate | Tool (`test-stack-profiles/spring-boot`) | Why |
|----------|-------|------|------------------------------------------|-----|
| Overdraft rule rejects an over-limit transfer | Unit | — | JUnit (no Spring context) | core domain logic, all branches |
| `TransferService` orchestrates rule + repo + publisher | Unit (sociable) | — | JUnit + stub repo/publisher | wiring of collaborators |
| `POST /transfers` maps request → 200/422, JSON shape | Component | — | MockMvc / `@WebMvcTest` | controller, validation, serialization — deps doubled |
| Repository persists + reads back correctly | Integration | — | Testcontainers (real DB) | the adapter/SQL actually works |
| Other services still accept our event/response shape | Contract | — | Spring Cloud Contract / Pact | cross-boundary agreement (`microservice-testing.md`) — not E2E |

## Quadrants (`testing-quadrants.md`)

Q1 strong ✓ · Q2 add a BDD acceptance example for "no overdraft" before coding · Q3 N/A (no UI) · **Q4** → security-review the auth on `/transfers`; load-test if it's a hot path.

## Techniques (`testing-techniques/`, on match)

Money math invariants (sum preserved across a transfer) → **property-based**. Resilience claim "degrades if the broker is down" → **chaos**.

## Notes

Keep the overdraft rule a **unit** test, not a MockMvc test — driving the HTTP layer to assert a calculation is the "testing through the UI for logic" anti-pattern. Cross-service agreement is a **contract** test, not a multi-service E2E (don't depend on provider cooperation — see `cd-test-architecture.md`).
