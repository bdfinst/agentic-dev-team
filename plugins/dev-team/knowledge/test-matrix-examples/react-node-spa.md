# Worked example — React SPA + Node/Express API

Few-shot template for `test-design-advisor`. Adapt the rows; don't copy verbatim. Feature: **a logged-in user submits a "place order" form and sees a confirmation**. Architecture is thin-logic glue over frameworks → **trophy** shape (`test-pyramid.md`).

## Pyramid placement (advisor output shape)

| Behavior | Layer | Gate | Tool (`test-stack-profiles/`) | Why |
|----------|-------|------|-------------------------------|-----|
| Order total + tax calculation | Unit | — | Vitest/Jest (`node`, `react`) | pure logic, edge cases |
| `POST /orders` persists + returns 201 | Integration | — | supertest + test DB (`node`) | route, validation, persistence wiring |
| Order form renders + disables submit while pending | Component | — | Testing Library + MSW (`react`) | DOM, wiring, async state — API mocked |
| User submits and sees confirmation | E2E | ↑E2E (Gate A) | Playwright (`react`) | user acts and must *see* the rendered result — amortize into the existing checkout journey |

## Quadrants (`testing-quadrants.md`)

Q1 unit+integration+component ✓ · Q2 the E2E journey doubles as an acceptance example ✓ · **Q3 empty** → charter one exploratory session on the checkout flow · **Q4** → add a load check on `POST /orders` if it's hot.

## Techniques (`testing-techniques/`, on match)

Order-total invariants (never negative, tax ≤ total) → **property-based**. Payload from an untrusted client → **schema-validation** on the request body.

## Notes

One E2E for the journey, not one per field — field validation is a component/unit concern (avoid the ice-cream cone). The fat integration+component middle is correct for this architecture, not an hourglass.
