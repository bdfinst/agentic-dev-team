# Test Layer Gates

Reference file for the `test-design-advisor` skill. The pyramid heuristic (`test-pyramid.md`) picks the *lowest* layer that verifies a behavior. These **pre-gates** run first and **escalate upward only** — never lower the pick — when a behavior can break in a way the lowest layer misses (Swiss-cheese model).

Layers match `test-pyramid.md` (unit / integration / component / contract / E2E) and map to `cd-test-architecture.md`'s six test types — see its *Terminology Reconciliation* section.

**business-critical** = labelled so in the input, or confirmed when the advisor asks. The redundancy check fires only on a positive determination.

---

## The gates (before pyramid placement)

**Gate A — user-facing dynamic.** The user acts and must *see* a rendered result. → E2E **alongside** lower layers. State the slow/flaky cost; amortize by extending or grouping into a journey test.

**Gate B — bug-fix regression.** → regression at the **layer the bug was discovered** (browser → E2E; unit-debug → unit). Must fail on old code, pass on the fix. Never escalates above the discovery layer.

**Gate C — dynamic-swap delivery chain.** An HTMX / Alpine / Turbo / LiveWire swap. → browser test **REQUIRED** (not "recommended"); integration is complementary, not sufficient. Holds with no server state change too (structural seam: wrong `hx-target`, stale swap, re-init).

**Gate D — visual fidelity.** Output whose layout/appearance matters (PDF, print, email, receipt). With a reference: approval (text) and/or screenshot (CSS/layout), surfacing maintenance cost. No reference: manual review + suggest creating one.

---

## Redundancy check (business-critical only, after placement)

A business-critical behavior at only one layer → flag it, name a second layer with a **different failure mode**, and give a concrete recommendation. Catches/misses:

| Layer | Catches | Misses |
|-------|---------|--------|
| Unit | logic, edge cases | wiring, integration, UI |
| Integration | routing, persistence, security | client behavior, rendering |
| Component/Frontend | wiring, DOM, attributes | backend logic, real network |
| Contract | API-shape drift | semantic/business bugs |
| E2E | full-stack, real browser | slow, flaky, poor localization |

When a gate mandates application-level E2E, **flag the seam (`→ cd-test-architecture`) and defer the harness/pipeline design** to `cd-test-architecture`. This file stays at unit/module altitude.
