# Fixture: test-layer-gates expected gate firings

Verification fixture for the behavior pre-gates added to the `test-design-advisor` skill (issue #80).
Each row is a behavior the advisor may be asked to design tests for, the gate(s) expected to fire, and the
expected resulting layer(s). The Step 3 walk-through runs the advisor against each row and records
actual == expected. This is the reviewer-rerunnable spec the gates are written to satisfy.

Layer vocabulary matches `knowledge/test-pyramid.md`: unit / integration / component / contract / E2E.
Gate-column sentinels: `—` (no gate), `↑<layer>` (escalated), `→ cd-test-architecture` (E2E architecture deferred).

| # | Behavior | Pre-Step-2 (lowest layer) | Gate(s) expected | Expected layer(s) | Notes / required output |
|---|----------|---------------------------|------------------|-------------------|--------------------------|
| 1 | Pure function: format a currency amount from cents | unit | none (`—`) | unit | Gates silent; Step 2 pick stands; Gate cell `—` |
| 2 | Click "Add to cart" updates the cart badge the user sees | unit/integration | A | `↑ E2E` + lower layers; `→ cd-test-architecture` | E2E recommended *alongside* lower layers; cost trade-off + ≥1 amortization (extend a journey / group behaviors) |
| 3 | Bug fix: discount miscalculated, found by a user in the browser | unit | B | `↑ E2E` | Regression at discovery (E2E) layer; must fail-on-old / pass-on-new |
| 4 | Bug fix: off-by-one in a parser, found while unit-testing | unit | B (negative) | unit | Gate B anchors at discovery layer = unit; **no** E2E escalation |
| 5 | HTMX swap re-renders the order total after a server-side DB write | integration | C | `↑ E2E` REQUIRED; `→ cd-test-architecture` | Browser test REQUIRED (not "recommended"); integration labelled complementary |
| 6 | Alpine toggle shows/hides a panel, no server call | component/frontend | C (structural) | `↑ E2E` REQUIRED | Browser REQUIRED for the structural seam; rationale cites wrong hx-target / stale swap / re-init |
| 7 | Generate a printable invoice PDF; a reference mockup exists | unit | D | unit + approval and/or screenshot | Approval for text output; screenshot when CSS/layout fidelity matters; both surface maintenance cost |
| 8 | Render an email template; no reference exists | unit | D (no-ref) | unit + manual | Manual visual review; suggest creating a reference to enable future automation |
| 9 | Business-critical: funds-transfer amount calculation, covered only by a unit test | unit | redundancy | unit + a 2nd layer | Flags single-layer coverage; names a different-failure-mode layer + a concrete recommendation (e.g. integration for persistence/transaction) |
| 10 | Both user-facing dynamic AND a browser-found bug fix (multi-gate) | integration | A + B | `↑ E2E` (union, no duplicate) | Layers unioned, no double-count; each gate's cost listed once; reconciliation guidance if amortization advice differs |
| 11 | Behavior whose dynamic-ness is genuinely unclear from the description | (deferred) | ambiguity | (pending answer) | Advisor states its assumption, asks once (batched), offers "treat all ambiguous as dynamic", never silently escalates |

## Walk-through log (filled during Step 3)

For each row, record the advisor's actual gate firing(s) and layer(s). Any mismatch → fix gate wording and re-run.

| # | Actual gate(s) | Actual layer(s) | Match? |
|---|----------------|-----------------|--------|
| 1 |  |  |  |
| 2 |  |  |  |
| 3 |  |  |  |
| 4 |  |  |  |
| 5 |  |  |  |
| 6 |  |  |  |
| 7 |  |  |  |
| 8 |  |  |  |
| 9 |  |  |  |
| 10 |  |  |  |
| 11 |  |  |  |
