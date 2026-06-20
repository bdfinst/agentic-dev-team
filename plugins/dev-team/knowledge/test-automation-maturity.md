# Test Automation Maturity

Reference file for `test-review` and the `test-health` skill (project-wide audit). It answers one question: **how maintainable is this suite as it grows, and where does it sit on the maturity curve?**

**Scope boundary — three files share "test automation"; keep them disjoint:**

- `test-strategy.md` owns the automation **strategy** axis (Scripted / Data-Driven / Recorded, fixture lifecycle, SUT interaction). Do not restate it here — cross-link.
- `test-refactoring.md` owns the **goals & principles** (self-checking, isolated, one-condition-per-test, design-for-testability). Do not restate them here — cross-link.
- **This file** owns only the **maturity diagnostic** and the **abstraction patterns** below.

Source: Meszaros *xUnit Test Patterns*; Crispin & Gregory; Page Object (Fowler/Selenium); Screenplay (Marcano). Stack-agnostic.

---

## Maturity scale (diagnose from evidence, lowest rung first)

| Rung | Signal in the suite | Risk |
|------|---------------------|------|
| **0 — Manual / recorded** | record-and-replay scripts, no hand-written assertions | brittle; re-record on every UI change |
| **1 — Scripted, raw** | hand-written tests, but selectors/URLs/payloads inline in every test | one change touches many files |
| **2 — Abstracted** | a layer between tests and the SUT (Page Objects / API client / DSL); tests read in domain terms | maintainable; the target for most suites |
| **3 — Screenplay / actor** | behaviour expressed as actor tasks/questions, reusable across suites | worth it only for large E2E suites; over-engineering below ~50 E2E tests |

Report the rung from observed evidence (grep for duplicated selectors/literals, presence of a `pages/`/`support/` layer), then recommend the **next** rung — never skip ahead.

---

## Single-Point-of-Change test

Pick one volatile detail (a CSS selector, an endpoint path, a field name). Count how many test files would change if it changed once.

- **N files → broken by one rename** is the headline maturity metric. N=1 is healthy; N≫1 is rung 1.
- Fix: extract that detail behind one abstraction (Page Object method, API client, builder) so the rename lands in **one** place.

## Abstraction patterns

- **Page Object / API client / DSL** — a façade exposing domain actions (`loginAs(user)`, `placeOrder(...)`), hiding selectors/HTTP. The standard rung-2 move.
- **Screenplay** — actors perform tasks and ask questions; tasks compose. Use for large, cross-cutting E2E suites only.

## Smell: UI-based setup

Driving the **UI** to establish preconditions (clicking through signup just to test checkout) is slow and flaky. Set state through the back door — API, fixture, or seeded DB — and reserve UI steps for the behaviour under test. (Back-door *setup* is legitimate; see `test-strategy.md` → SUT Interaction. It is not the banned "test logic in production" smell.)

## Graduated disclosure (don't over-build)

Scale abstraction to suite size, not aspiration:

| Test count (a given type) | Recommend |
|---------------------------|-----------|
| < ~10 | inline is fine; abstracting early is premature |
| ~10–50 | extract Page Objects / a client / builders (rung 2) |
| > ~50 E2E | consider Screenplay (rung 3) |

## Boundaries

Maturity is about **maintainability under change**, not coverage or correctness — those are `farley-score` and `test-review`. A small suite at rung 1 is fine; flag low maturity only when suite size makes the single-point-of-change cost real.
