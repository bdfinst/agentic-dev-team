# Stack profile — .NET (C#)

Resolves `test-design-advisor`'s abstract layer (`test-pyramid.md`) to the canonical .NET tool.

| Layer | Tool | How to assert |
|-------|------|---------------|
| Unit | xUnit (or NUnit) + FluentAssertions; Moq / NSubstitute | call the class directly; inject collaborators |
| Component / Service | `WebApplicationFactory<TEntryPoint>` (in-memory `TestServer`) + `HttpClient` | drive the API in-process; replace externals in the test host's DI |
| Integration | Testcontainers-dotnet (real DB/broker) or `EF Core` against a real provider | repository/EF mappings/SQL against a real dependency |
| Contract | PactNet | consumer↔provider agreement (`microservice-testing.md`) |
| E2E | Playwright for .NET | critical journeys only |

**Notes.** Override services in `WebApplicationFactory.WithWebHostBuilder(...ConfigureTestServices)` to double outbound dependencies pre-merge without config. Inject `TimeProvider` (or an `IClock`) for time determinism; never `DateTime.Now` in logic. Avoid the in-memory EF provider for anything relational — it hides SQL bugs; use Testcontainers or SQLite-in-memory deliberately and know its limits.
