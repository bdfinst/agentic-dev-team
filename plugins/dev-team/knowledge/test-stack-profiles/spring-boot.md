# Stack profile — Spring Boot (Java/Kotlin)

Resolves `test-design-advisor`'s abstract layer (`test-pyramid.md`) to the canonical Spring tool. Names tools by role; pick the team's actual assertion library.

| Layer | Tool | How to assert |
|-------|------|---------------|
| Unit | JUnit 5 + AssertJ; Mockito for collaborators | call the class directly, **no Spring context** — keep it fast |
| Component / Service | `@WebMvcTest` + MockMvc (web slice) or `@SpringBootTest(webEnvironment=RANDOM_PORT)` + TestRestTemplate | drive the endpoint in-process; double the service's own externals |
| Integration | Testcontainers (real DB/broker) + `@DataJpaTest` / `@SpringBootTest` | assert the adapter/SQL/serialization against a real dependency |
| Contract | Spring Cloud Contract or Pact | verify consumer↔provider agreement (`microservice-testing.md`), not E2E |
| E2E | Playwright / Selenium against the deployed app | critical journeys only |
| BDD (optional) | Cucumber-JVM — component/service scenarios | `.feature` files run inside JUnit 5 via `cucumber-junit-platform-engine` |

**Notes.** Prefer slice annotations (`@WebMvcTest`, `@DataJpaTest`) over full `@SpringBootTest` — faster context, sharper scope. Inject a fixed `Clock` bean for time determinism. Wrap third-party clients in an owned adapter and double the adapter (`cd-test-architecture.md`), never the SDK. Kotlin: same tools; MockK is an idiomatic alternative to Mockito.

**BDD.** Use Cucumber-JVM when non-technical stakeholders need to read or co-author scenarios (see `../references/bdd-value-guide.md` for the decision rubric). Wire it via `cucumber-junit-platform-engine` so Cucumber runs inside JUnit 5 — Maven Surefire and the Gradle `test` task pick it up automatically (the Maven and Gradle dependency sets differ slightly). Full wiring for both build tools and the `PendingException` stub: `bdd-frameworks.md`.
