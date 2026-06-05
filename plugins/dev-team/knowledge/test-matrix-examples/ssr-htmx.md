# Worked example — SSR + HTMX dynamic swap

Few-shot template for `test-design-advisor`. Adapt the rows. Feature: **clicking "Add to cart" sends an HTMX `POST`, the server mutates the cart and returns an HTML fragment that swaps the cart badge**. The client-side swap seam is the point of risk → **Gate C fires** (`test-layer-gates.md`).

## Pyramid placement (advisor output shape)

| Behavior | Layer | Gate | Tool (`test-stack-profiles/ssr-htmx`) | Why |
|----------|-------|------|---------------------------------------|-----|
| Cart total recomputed after add | Unit | — | server-side unit (`django`/`node`) | pure logic |
| `POST /cart` mutates state + renders the fragment | Integration | — | TestClient / supertest | handler + template render + persistence |
| Returned fragment carries the right `hx-target`/`hx-swap` | Component | — | JSDOM + parse the HTML (`ssr-htmx`) | template/wiring assertions, no browser |
| Badge actually updates in the page after the swap | **Browser (REQUIRED)** | ↑E2E (Gate C) | Playwright | the swap seam — `hx-target`, stale swap, re-init — gets **zero** coverage from integration |

## Quadrants (`testing-quadrants.md`)

Q1/Q2 ✓ · Q3 → exploratory pass on rapid double-clicks and back-button state · Q4 → none unless the endpoint is hot.

## Techniques (`testing-techniques/`, on match)

If the swapped fragment's visual layout matters (a styled receipt) → **screenshot**; if it's text/markup correctness → **approval** on the rendered fragment.

## Notes

Gate C marks the browser test **required, not recommended** — integration verifies the server returns *a* fragment, never that the client wired it into the DOM correctly. The advisor flags the E2E requirement and defers harness/pipeline design to `cd-test-architecture`; it does not design the Playwright setup here.
