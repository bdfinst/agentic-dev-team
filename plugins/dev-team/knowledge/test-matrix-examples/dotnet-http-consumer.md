# Worked example — ASP.NET Core service calling a third-party HTTP API

Few-shot template for `test-design-advisor`. Adapt the rows. Feature:
**an ASP.NET Core 8 service exposes `POST /orders`; the order handler calls
an upstream third-party Pricing API over HTTPS (JSON), then persists the
order to its own SQL store via EF Core; the Pricing API is owned by another
company — no provider cooperation, no CDC tooling on their side — and is
flakier than the team's own services**. This is the common
[API Consumer pattern](../component-test-patterns.md#api-consumer); the
pre-merge gate must not depend on the upstream being reachable, and the
consumer must survive provider breakage without notice.

Layer names use the MinimumCD six test types from
`knowledge/cd-test-architecture.md` § *The Six Test Types*. Mechanics for
the outbound HTTP layer are from
`knowledge/references/csharp-http-client-testing.md`; tool resolution is from
`knowledge/test-stack-profiles/dotnet.md`.

## Adapter shape (the seam under test)

`IPricingClient` is the team-owned thin adapter (Adapter Rule, see
`knowledge/cd-test-architecture.md#the-adapter-rule-own-your-boundaries`):

```csharp
public interface IPricingClient
{
    Task<Money> QuoteAsync(Sku sku, CancellationToken ct);
}

internal sealed class PricingClient : IPricingClient
{
    private readonly HttpClient _http;          // injected; primary handler is swappable
    private readonly TimeProvider _time;        // determinism (Polly + tests)
    public PricingClient(HttpClient http, TimeProvider time) { _http = http; _time = time; }
    // ...
}
```

Wired in production with `services.AddHttpClient<IPricingClient, PricingClient>(...)`;
in tests, `ConfigurePrimaryHttpMessageHandler(() => stub)` swaps only the
leaf. The adapter is the single place every "the real thing changed" failure
localizes to.

## Pyramid placement (advisor output shape)

| Behavior | Layer | Gate | Tool (`test-stack-profiles/dotnet`) | Why this layer (not the one above or below) |
|----------|-------|------|--------------------------------------|---------------------------------------------|
| `Money` arithmetic invariants (sum preserved, no negative quotes) | Unit | — | xUnit + FluentAssertions; **property-based** via FsCheck on the invariant | pure value-object logic; a component test would only re-execute the same arithmetic through HTTP |
| `OrderDomainService` orchestrates pricing + persistence (no over-limit) | Unit (sociable) | — | xUnit + stub `IPricingClient`, in-memory repo | wires collaborators; a component test would re-execute the same orchestration through HTTP for no extra signal |
| `PricingClient` builds the correct request (method, path, query, auth header, `Idempotency-Key`, JSON body) and parses the success response | **Contract** | — | xUnit + `StubHttpMessageHandler` capturing `Requests`; structural JSON compare (`knowledge/references/csharp-http-client-testing.md`) | pins request/response shape at the boundary; a unit test of the adapter would not exercise serialization/headers, an integration test would couple the gate to a running provider we don't control |
| `PricingClient` maps non-2xx (`401`, `404`, `422`, `500`) to typed domain errors | **Contract** | — | xUnit + `StubHttpMessageHandler` returning each status | failure-mapping IS the contract; a component test would only re-prove the same mapping through HTTP |
| `PricingClient` survives provider flake: retries `503` per Polly policy, opens circuit-breaker after sustained failure, enforces deadline, fast-fails on half-open | **Component** (resilience) | — | xUnit + `StubHttpMessageHandler` queue `[503,503,200]` etc. + `FakeTimeProvider` + Polly v8 pipeline bound to that `TimeProvider` | the resilience policy is the behavior under test; running against the real provider is non-deterministic and would never be a gate; lower than full HTTP component test because no inbound HTTP is needed to verify the outbound seam |
| `POST /orders` end-to-end through middleware, validation, controller, doubled pricing adapter, in-memory repo | Component | — | `WebApplicationFactory<Program>` + `HttpClient`; register stub `IPricingClient` in `ConfigureTestServices` | exercises the assembled in-process app deterministically; a contract test cannot cover request validation + controller wiring + auth pipeline together; an E2E test would need the real Pricing API |
| EF Core `OrderRepository` SQL against the real SQL flavor (column types, isolation, EF-generated SQL) | Integration (Stage 1 / 2, NOT pre-merge) | off-gate | xUnit + Testcontainers (PG / SQL Server) | the in-memory EF provider hides SQL bugs; the real engine is non-deterministic / requires a container ⇒ never gates the merge per MinimumCD |
| The team's hand-rolled `PricingClient` double has not drifted from the real Pricing API | **Scheduled provider verification** | out-of-band (nightly) | xUnit run vs the provider's real *non-prod* endpoint, decoupled from deploys (`cd-test-architecture.md#double-validation-keeping-doubles-honest`) | proves the double still matches reality; lower-layer contract tests cannot, by construction, observe provider drift; we **do not assume provider cooperation** so consumer-owned detection is the only defense |
| Critical user journey: a successful order across the real deployed system (pricing + persistence + downstream notification) | E2E | post-deploy smoke | one Playwright/HTTP scenario in a deployed environment | (1) contract tests cannot cover real multi-service propagation; (2) component test stubs the pricing adapter; (3) resilience covers failure modes, not the happy path across real services; (4) the order-confirmed journey is a critical real-component crossing — non-deterministic, NEVER pre-merge per MinimumCD |

## E2E justification (only the last row)

The advisor's E2E justification block for this matrix lists exactly one
behavior. Every other row above shows how the four-condition gate forces a
lower layer.

## Doubles strategy

| Test | Collaborator | Double | Verify by |
|------|--------------|--------|-----------|
| `OrderDomainService` unit | `IPricingClient` | Stub | State (returned `Order`) |
| `OrderDomainService` unit | `IOrderRepository` | Stub | State (returned `Order`) |
| `PricingClient` contract — success | `HttpMessageHandler` | `StubHttpMessageHandler` returning canned 200 | State: captured `Requests[0]` (method/path/headers/JSON body) + returned `Money` |
| `PricingClient` contract — non-2xx | `HttpMessageHandler` | Stub returning each status | State: typed domain error thrown |
| `PricingClient` resilience | `HttpMessageHandler` + `TimeProvider` | Stub queue + `FakeTimeProvider`; Polly bound to it | State: final outcome + `Requests.Count` (proves retry count) |
| `POST /orders` component | `IPricingClient` | Stub registered via `ConfigureTestServices` | State (HTTP 200 + persisted order via in-memory repo) |
| `POST /orders` component | `IOrderRepository` | In-memory fake | State (persisted row) |
| Scheduled provider verification | the real Pricing API | None — real provider, real network, non-prod env | Schema + status agreement |

Default to state verification and the simplest double per
`knowledge/test-doubles.md`. The stub handler's captured `Requests` list IS
the state surface — never reach for a behavior mock on `HttpMessageHandler`.

## Techniques overlay (`testing-techniques/`)

- Money arithmetic invariants → **property-based** (`property-based.md`).
- Pricing API responds with JSON governed by an OpenAPI schema →
  **schema-validation** at the contract layer (`schema-validation.md`).
- "Service degrades but stays up when Pricing is down for 30s" →
  **chaos** at the adapter seam (`chaos.md`), realized by the
  `StubHttpMessageHandler` returning timeouts/errors.

## Smells to refactor away first

Cross-referenced with
`knowledge/references/csharp-http-client-testing.md` §
*Common smells in C# HTTP-consumer tests*:

- A `Mock<HttpClient>` in any test → wrap in an adapter and double the
  `HttpMessageHandler`.
- A `Mock<IThirdPartyPricingSdk>` directly → own the adapter; double the
  adapter or its `HttpMessageHandler`.
- `Thread.Sleep(...)` or `await Task.Delay(...)` waiting for a retry →
  introduce `TimeProvider` + Polly v8 bound to `FakeTimeProvider`.
- `Assert.Equal("""{"sku":"X"}""", actualJson)` → deserialize and compare
  structurally.
- A test that needs `appsettings.Test.json` with a real Pricing API URL →
  the test is mis-typed; route it to the scheduled provider verification
  job, not the pre-merge gate.

## Quadrants (`testing-quadrants.md`)

Q1 strong ✓ · Q2 add a BDD acceptance example for "order rejected when
pricing fails three times" (Reqnroll; see
`../test-stack-profiles/dotnet.md` BDD row) · Q3 minimal (API, no UI) ·
**Q4** → security-review auth/secret handling on the Pricing API
connection; resilience claims under provider outage cited in any SLO
documentation.

## Notes

- The contract tests for `PricingClient` are always pre-merge — they're
  deterministic, in-process, microsecond-fast. The provider-verification
  job is always **off the gate** — it's the *detection* loop for drift,
  and it must run on a clock the build doesn't depend on.
- Resilience component tests with `FakeTimeProvider` complete in
  microseconds even when the policy says "wait 30s then retry" — the
  Polly pipeline must be configured with that `TimeProvider` for this to
  hold. If a resilience test takes longer than the others, the wiring is
  wrong, not the policy.
- The single E2E test exists because no lower layer can prove order
  propagation across the real Pricing API and real downstream notification.
  Adding a second E2E "to be thorough" would fail the four-condition gate
  (`cd-test-architecture.md#the-e2e-justification-gate`).
