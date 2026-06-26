# Stack profile — Node.js backend (Express/Fastify/Nest)

Resolves `test-design-advisor`'s abstract layer (`test-pyramid.md`) to the canonical Node tool. For the browser/UI side see `react.md` / `vue.md` / `ssr-htmx.md`.

| Layer | Tool | How to assert |
|-------|------|---------------|
| Unit | Vitest or Jest (or `node:test`); function-level doubles | call the module directly; fake timers for time |
| Component / Service | supertest against the app instance (no live port) + MSW for outbound HTTP | drive the route in-process; double the service's externals |
| Integration | Testcontainers (real DB/broker) or an ephemeral DB | the repository/driver/SQL/serialization actually works |
| Contract | Pact (JS) or `openapi`-driven checks | consumer↔provider agreement (`microservice-testing.md`) |
| E2E | Playwright | critical journeys only |
| BDD (optional) | Cucumber.js — component/service scenarios | `.feature` files with step defs in `features/support/`; drives the public surface via supertest |

**Notes.** `supertest(app)` exercises the full middleware/routing stack in-process — the workhorse component test. Mock outbound HTTP with **MSW** (request-level) rather than stubbing the HTTP client, so serialization is real. Fake timers (`vi.useFakeTimers()` / `jest.useFakeTimers()`) and inject a clock for determinism. Nest: use `Test.createTestingModule(...)` to assemble the component with doubled providers.

**BDD.** Use Cucumber.js when non-technical stakeholders need to read or co-author scenarios (see `references/bdd-value-guide.md` for the decision rubric). Wire Cucumber.js **alongside** your existing Vitest/Jest suite — they are complementary, not alternatives: Cucumber drives the public surface (typically through supertest), xUnit drives internals. Install (`@cucumber/cucumber`) and the `this.pending()` stub: `bdd-frameworks.md`.
