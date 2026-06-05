# Stack profile — Node.js backend (Express/Fastify/Nest)

Resolves `test-design-advisor`'s abstract layer (`test-pyramid.md`) to the canonical Node tool. For the browser/UI side see `react.md` / `vue.md` / `ssr-htmx.md`.

| Layer | Tool | How to assert |
|-------|------|---------------|
| Unit | Vitest or Jest (or `node:test`); function-level doubles | call the module directly; fake timers for time |
| Component / Service | supertest against the app instance (no live port) + MSW for outbound HTTP | drive the route in-process; double the service's externals |
| Integration | Testcontainers (real DB/broker) or an ephemeral DB | the repository/driver/SQL/serialization actually works |
| Contract | Pact (JS) or `openapi`-driven checks | consumer↔provider agreement (`microservice-testing.md`) |
| E2E | Playwright | critical journeys only |

**Notes.** `supertest(app)` exercises the full middleware/routing stack in-process — the workhorse component test. Mock outbound HTTP with **MSW** (request-level) rather than stubbing the HTTP client, so serialization is real. Fake timers (`vi.useFakeTimers()` / `jest.useFakeTimers()`) and inject a clock for determinism. Nest: use `Test.createTestingModule(...)` to assemble the component with doubled providers.
