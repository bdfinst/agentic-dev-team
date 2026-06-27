# Stack profile — Vue (CSR / SPA)

Resolves `test-design-advisor`'s abstract layer (`test-pyramid.md`) for a client-side Vue app. Backend layers live in `node.md` (or the API's profile).

| Layer | Tool | How to assert |
|-------|------|---------------|
| Unit | Vitest | composables/stores (Pinia)/utils called directly — no mount |
| Component | Vue Testing Library (preferred) or `@vue/test-utils` + **MSW** | mount, interact via role/label queries, assert on rendered DOM; API mocked at the network |
| Integration (UI↔API) | Testing Library + MSW with realistic handlers | fetching, store wiring, error/loading states |
| E2E | Playwright / Cypress | critical journeys only |

**Notes.** Prefer **Vue Testing Library** (role/label queries) over `test-utils`' `findComponent`/`wrapper.vm` access — querying by what the user sees is more resilient and a11y-aware (`a11y-review`). Mock the network with **MSW**, not stubbed `fetch`/`axios`. Test Pinia stores as plain units. For visual fidelity use `../testing-techniques/screenshot.md`; don't lean on full-DOM snapshots for correctness.
