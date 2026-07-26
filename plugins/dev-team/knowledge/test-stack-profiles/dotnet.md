# Stack profile — .NET (C#)

Resolves `test-design-advisor`'s abstract layer (`test-pyramid.md`) to the canonical .NET tool.

| Layer | Tool | How to assert |
|-------|------|---------------|
| Unit | xUnit (or NUnit) + FluentAssertions; Moq / NSubstitute | call the class directly; inject collaborators |
| Component / Service (API Provider — inbound HTTP) | `WebApplicationFactory<TEntryPoint>` (in-memory `TestServer`) + `HttpClient` | drive the API in-process; replace externals in the test host's DI |
| Component / Service (API Consumer — outbound HTTP) | Stub `HttpMessageHandler` + `IHttpClientFactory` (`ConfigurePrimaryHttpMessageHandler`) + Polly bound to `FakeTimeProvider` | drive the adapter; assert request shape captured by the stub + the resilience policy under doubled failures (`../references/csharp-http-client-testing.md`) |
| Integration | Testcontainers-dotnet (real DB/broker) or `EF Core` against a real provider | repository/EF mappings/SQL against a real dependency |
| Contract (HTTP — request/response shape) | Stub `HttpMessageHandler` driving the owned adapter | structural deserialization of captured request + canned response; queue retry sequences (`../references/csharp-http-client-testing.md`) |
| Contract (consumer↔provider agreement) | PactNet | consumer-driven contracts across owned service boundaries (`microservice-testing.md`) |
| E2E | Playwright for .NET | critical journeys only |
| BDD (optional) | Reqnroll — Unit + Component scenarios | `[Binding]` step classes bound to `.feature` files; runs on xUnit/NUnit/MSTest |

**Notes.** Override services in `WebApplicationFactory.WithWebHostBuilder(...ConfigureTestServices)` to double outbound dependencies pre-merge without config. Inject `TimeProvider` (or an `IClock`) for time determinism; never `DateTime.Now` in logic — pair with Polly v8 bound to the same `TimeProvider` so retry/backoff/circuit-breaker policies advance virtual time deterministically. For the **API Consumer** side (your service calling out), the canonical pre-merge seam is `HttpMessageHandler` — not `WebApplicationFactory`, not Kestrel on a port — wrapped behind a thin owned adapter; WireMock.Net is the preferred implementation of that seam when installed — the same `IHttpClientFactory`/`ConfigurePrimaryHttpMessageHandler` configuration point is used to point the client at WireMock.Net's server URL, but the resulting call is a real loopback HTTP request, not an in-memory interception — with the hand-rolled `StubHttpMessageHandler` kept as backup; see `../references/csharp-http-client-testing.md` for the full pattern (`StubHttpMessageHandler`, request-shape assertions, retry sequencing, off-the-shelf alternatives, smells, and the WireMock.Net preferred/backup detail, including the loopback-socket reconciliation). Avoid the in-memory EF provider for anything relational — it hides SQL bugs; use Testcontainers or SQLite-in-memory deliberately and know its limits.

**BDD.** Use Reqnroll when non-technical stakeholders need to read or co-author scenarios (see `../references/bdd-value-guide.md` for the decision rubric) — BDD scenarios typically sit at the Unit and Component boundaries. **Prefer Reqnroll over SpecFlow:** identical API, but SpecFlow requires a commercial license for teams larger than one, while Reqnroll is the MIT-licensed, actively-maintained fork. Install (`dotnet add package Reqnroll.xUnit` / `.NUnit` / `.MsTest`) and the `ScenarioContext.StepIsPending()` stub: `bdd-frameworks.md`.
