# Stack profile — SSR + HTMX / Alpine / Turbo

Resolves `test-design-advisor`'s abstract layer (`test-pyramid.md`) for server-rendered apps with hypermedia-driven dynamic swaps. The server uses its own stack profile (`spring-boot` / `django` / `node` / …); this profile covers the **frontend/swap** layer those don't.

| Layer | Tool | How to assert |
|-------|------|---------------|
| Unit (server) | the server stack's unit tools | template-data/logic |
| Integration (server) | the server's component tools (TestClient/MockMvc/supertest) | the endpoint mutates state and returns the **right HTML fragment** |
| Frontend (template/wiring) | **JSDOM + MSW** — parse the rendered fragment in Node | the fragment carries the correct `hx-target` / `hx-swap` / `hx-trigger` / Alpine `x-data` attributes, without a browser |
| Browser (swap seam) | **Playwright (REQUIRED — Gate C)** | the swap actually updates the DOM in a real browser: right target, no stale swap, scripts re-init after swap |

**Recipe — testing the swap without a browser (the cheap 80%).** Request the fragment from the server (or render the template), load the HTML into **JSDOM**, and assert the hypermedia attributes and structure. This catches wrong/missing `hx-*` wiring fast and deterministically. It does **not** prove the browser applies the swap — that is Gate C's required Playwright test (`test-layer-gates.md`), because integration gives the client-side seam *zero* coverage.

**Notes.** Don't unit-test HTMX itself — test *your* attributes and *your* fragment. Visual fidelity of a swapped fragment → `testing-techniques/screenshot.md`; markup correctness → `approval.md`. The advisor flags the browser requirement and defers harness/pipeline design to `cd-test-architecture`.
