# Stack profile — .NET (C#)

Resolves `test-design-advisor`'s abstract layer (`test-pyramid.md`) to the canonical .NET tool.

| Layer | Tool | How to assert |
|-------|------|---------------|
| Unit | xUnit (or NUnit) + FluentAssertions; Moq / NSubstitute | call the class directly; inject collaborators |
| Component / Service | `WebApplicationFactory<TEntryPoint>` (in-memory `TestServer`) + `HttpClient` | drive the API in-process; replace externals in the test host's DI |
| Integration | Testcontainers-dotnet (real DB/broker) or `EF Core` against a real provider | repository/EF mappings/SQL against a real dependency |
| Contract | PactNet | consumer↔provider agreement (`microservice-testing.md`) |
| E2E | Playwright for .NET | critical journeys only |
| BDD (optional) | Reqnroll — Unit + Component scenarios | `[Binding]` step classes bound to `.feature` files; runs on xUnit/NUnit/MSTest |

**Notes.** Override services in `WebApplicationFactory.WithWebHostBuilder(...ConfigureTestServices)` to double outbound dependencies pre-merge without config. Inject `TimeProvider` (or an `IClock`) for time determinism; never `DateTime.Now` in logic. Avoid the in-memory EF provider for anything relational — it hides SQL bugs; use Testcontainers or SQLite-in-memory deliberately and know its limits.

**BDD.** Use Reqnroll when non-technical stakeholders need to read or co-author scenarios (see `references/bdd-value-guide.md` for the decision rubric) — BDD scenarios typically sit at the Unit and Component boundaries. **Prefer Reqnroll over SpecFlow:** identical API, but SpecFlow requires a commercial license for teams larger than one, while Reqnroll is the MIT-licensed, actively-maintained fork. Install (`dotnet add package Reqnroll.xUnit` / `.NUnit` / `.MsTest`) and the `ScenarioContext.StepIsPending()` stub: `bdd-frameworks.md`.
