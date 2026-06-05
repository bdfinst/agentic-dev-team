# Worked example — Django API + scheduled batch job

Few-shot template for `test-design-advisor`. Adapt the rows. Feature: **a nightly job reads pending invoices, charges a payment gateway through an owned adapter, and emails receipts**. Orchestration/adapter-heavy, little domain logic → **diamond** shape (`test-pyramid.md`).

## Pyramid placement (advisor output shape)

| Behavior | Layer | Gate | Tool (`test-stack-profiles/django`) | Why |
|----------|-------|------|-------------------------------------|-----|
| "Invoice is due" predicate | Unit | — | pytest | the one bit of real logic |
| Job selects due invoices, skips paid, marks charged | Component | — | pytest + Django test DB, gateway/email **adapters doubled** | the orchestration — run pre-merge without real gateway |
| Payment adapter speaks the gateway's real protocol | Integration | — | pytest + recorded/contract sandbox | the adapter actually works (own your boundaries — `cd-test-architecture.md`) |
| Receipt PDF/email layout is correct | — | ↑ (Gate D) | approval (text) / screenshot (layout) | visual-fidelity artifact (`test-layer-gates.md`) |

## Quadrants (`testing-quadrants.md`)

Q1 thin (correctly — little logic) · Q2 acceptance example for the "skip already-paid" rule · Q3 N/A · **Q4 important** → resilience: what happens when the gateway times out mid-run? → **chaos**.

## Techniques (`testing-techniques/`, on match)

Gateway timeout/partial-failure resilience → **chaos**. Receipt email body vs a golden file → **approval**. Idempotency of a re-run after a crash → property/scenario coverage.

## Notes

The wide component middle is right for a diamond — the value is in orchestration, not unit logic; don't pad the unit base with tests that just exercise the framework. Double the **owned adapter**, never the gateway SDK directly (`cd-test-architecture.md` → the adapter rule).
