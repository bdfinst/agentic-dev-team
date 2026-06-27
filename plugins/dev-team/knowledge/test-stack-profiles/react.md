# Stack profile — React (CSR / SPA)

Resolves `test-design-advisor`'s abstract layer (`test-pyramid.md`) for a client-side React app. Backend layers live in `node.md` (or the API's own profile).

| Layer | Tool | How to assert |
|-------|------|---------------|
| Unit | Vitest/Jest | pure hooks/reducers/utils called directly — no render |
| Component | React Testing Library + **MSW** for network | render, interact via role/label queries, assert on the DOM the user sees; API mocked at the network |
| Integration (UI↔API) | RTL + MSW with realistic handlers, or a running test API | data fetching, cache, error/loading states |
| E2E | Playwright / Cypress against the running app | critical journeys only |

**Notes.** Query by **accessible role/label/text**, not test-ids or class names (resilient + doubles as an a11y check) — see `a11y-review`. Mock the network with **MSW**, not by stubbing `fetch`/`axios`, so serialization and request shape stay real. Don't snapshot whole component trees as a correctness crutch (brittle); for genuine visual fidelity use `../testing-techniques/screenshot.md`. Test behavior (what the user does/sees), never internal state or implementation details.
