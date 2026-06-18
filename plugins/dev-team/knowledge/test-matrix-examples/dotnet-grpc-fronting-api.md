# Worked example — ASP.NET Core API fronting gRPC microservices

Few-shot template for `test-design-advisor`. Adapt the rows. Feature:
**an ASP.NET Core 8 Web API fronts several owned gRPC microservices
(`AccountService`, `PaymentService`, `LedgerService`) behind hand-written
adapter ports; a SQL store via Dapper persists ledger entries; a
`POST /payments` endpoint authorizes the caller, debits the account via
`PaymentService`, writes a ledger entry via Dapper, and returns a result**.
This is a common payments / banking / e-commerce shape: rich domain logic
fronts multiple owned remote dependencies; the gate must stay deterministic
without standing up the back-end services.

Layer names use the MinimumCD six test types from
`knowledge/cd-test-architecture.md` § *The Six Test Types*.

## Pyramid placement (advisor output shape)

| Behavior | Layer | Gate | Tool (`test-stack-profiles/dotnet`) | Why this layer (not the one above or below) |
|----------|-------|------|--------------------------------------|---------------------------------------------|
| Authorization policy denies non-payer caller | Unit | — | xUnit + `AuthorizationHandlerContext` | pure policy logic; a component test would only re-execute the same code through HTTP middleware |
| `PaymentDomainService` orchestrates rule + debit + ledger (no over-limit) | Unit (sociable) | — | xUnit + stub adapters | wires collaborators; a component test would re-execute the same orchestration through HTTP for no extra signal |
| `IPaymentServiceAdapter` translates `DebitRequest` → gRPC request and `Ack` → domain reply | Contract | — | xUnit + in-memory gRPC channel (`Grpc.Core.Testing`) or stubbed `CallInvoker` | pin the request/response shape at the boundary; a unit test of the adapter would not exercise gRPC serialization, an integration test would couple the gate to a running provider |
| `PaymentServiceAdapter` survives a provider timeout / cancellation / malformed reply | Resilience | — | xUnit + simulated `CallInvoker` returning `RpcException`/timeout | failure-mode coverage at the seam; lower than a component test (no HTTP path needed), higher than a unit test (the adapter's failure translation IS the behavior under test) |
| `ILedgerRepository` (Dapper) writes + reads back a ledger row | Contract | — | xUnit + in-memory SQL fake (e.g. SQLite in-memory) | pins the SQL the adapter emits without the gate depending on a real container; a unit test cannot exercise SQL, an integration test moves it off the gate |
| `LedgerRepository` against the real SQL flavor (column types, isolation) | Integration (Stage 1 / 2, NOT pre-merge) | off-gate | xUnit + Testcontainers (MS SQL / PG) | the contract test pins shape but cannot prove the real engine accepts the SQL; non-deterministic / requires a container ⇒ never gates the merge per MinimumCD |
| `POST /payments` end-to-end through middleware, validation, controller, doubled adapters | Component | — | `WebApplicationFactory<Program>` + `HttpClient` + in-process double registrations (Test doubles for `IPaymentServiceAdapter`, `ILedgerRepository`) | exercises the assembled in-process app deterministically; a contract test cannot cover request validation + controller wiring + auth pipeline together; an E2E test would need the back-end services |
| Cross-cutting filter / exception middleware translates `DomainException` → 422 | Unit | — | xUnit + constructed `HttpContext` | the middleware IS the unit; a component test would only re-prove the same translation through HTTP |
| Other consumers still accept our `PaymentResult` response shape (and we still accept `PaymentService` reply shape) | Contract | — | Pact / Protobuf schema check against the provider's generated `.proto` (see `microservice-testing.md`) | cross-boundary agreement — never E2E; provider cooperation is not required |
| Provider adapters' in-memory doubles match the real provider | Scheduled provider verification | out-of-band | nightly job hitting provider test env | proves the in-memory double has not drifted from reality; lower-layer contract tests are insufficient on their own |
| Critical user journey: a successful payment + ledger write + downstream consumer sees the event (post-deploy) | E2E | post-deploy smoke | one Playwright/HTTP scenario in a deployed environment | (1) contract tests cannot cover the *real* multi-service propagation; (2) component test stubs all adapters; (3) resilience covers failure modes, not the happy path across real services; (4) the payment-confirmed journey is a critical real-component crossing — non-deterministic, NEVER pre-merge per MinimumCD |

## E2E justification (only the last row)

The advisor's E2E justification block for this matrix lists exactly one
behavior. The other rows show how the four-condition gate forces every
other behavior into a lower layer.

## Quadrants (`testing-quadrants.md`)

Q1 strong ✓ · Q2 add a BDD acceptance example for "deny over-limit" before
coding · Q3 minimal (API, no UI) · **Q4** → security-review the auth on
`/payments`; load-test if it's a hot path. For payments specifically:
PCI-DSS / SOC 2 coverage of the boundary level (contract pins, resilience
under provider outage, characterization for any legacy SQL touching
cardholder data) — flag to security-engineer if a `security-primitives`
contract is not yet in place.

## Doubles strategy

| Test | Collaborator | Double | Verify by |
|------|--------------|--------|-----------|
| `PaymentDomainService` unit | `IPaymentServiceAdapter` | Stub | State (returned `PaymentResult`) |
| `PaymentDomainService` unit | `ILedgerRepository` | Stub | State (returned `PaymentResult`) |
| `IPaymentServiceAdapter` contract | gRPC `CallInvoker` | In-memory fake / stubbed invoker | State (returned domain `Ack`) |
| `IPaymentServiceAdapter` resilience | gRPC `CallInvoker` | Stub that throws `RpcException`/timeout | State (translated domain error) |
| `ILedgerRepository` contract | SQL connection | In-memory SQL fake (SQLite) | State (round-trip row) |
| `POST /payments` component | `IPaymentServiceAdapter` | Stub registered in `WebApplicationFactory` | State (HTTP 200 + body) |
| `POST /payments` component | `ILedgerRepository` | Stub | State (HTTP 200 + body) |
| Provider contract | the real `PaymentService` provider | None (real provider in scheduled job) | Schema agreement |

Default to state verification and the simplest double per
`knowledge/test-doubles.md`. Use a mock/spy only when a true side-effect
boundary requires it (e.g. asserting "an audit event was published" when
the publisher is fire-and-forget).

## Techniques (`testing-techniques/`, on match)

Money math invariants (sum preserved across a transfer) →
**property-based**. Resilience claim "degrades if `PaymentService` is
down" → **chaos** at the adapter seam. Generated wire formats (proto3) →
**schema-validation** at the contract layer.

## Notes

- Keep the authorization policy a **unit** test, not a component test —
  driving HTTP middleware to prove the same `requirement.Succeed()` call
  is "testing through the UI for logic" anti-pattern.
- The **contract** tests for adapters pin shape and behavior; they are
  always pre-merge. The **integration** tests against Testcontainers /
  real providers prove the adapter's understanding of the real engine
  matches reality, and are always **off the gate**.
- The single **E2E** test exists because no other layer can prove the
  payment + ledger + downstream propagation across multiple owned
  services in a real environment. It runs post-deploy as smoke. Adding
  a second E2E "to be thorough" would fail the E2E justification gate.
- For regulated payment paths (card data, account numbers, secrets),
  confirm coverage at the boundary level — contract pins, resilience
  tests, and characterization tests for any legacy SQL paths handling
  cardholder data. Cite `knowledge/security-primitives-contract.md` if
  present; else flag the gap to `security-engineer`.
