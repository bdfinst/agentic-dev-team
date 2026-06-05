# Fixture: test-layer-gates expected gate firings

Verification fixture for the behavior pre-gates added to the `test-design-advisor` skill (issue #80).
Each row is a behavior the advisor may be asked to design tests for, the gate(s) expected to fire, and the
expected resulting layer(s). The Step 3 walk-through runs the advisor against each row and records
actual == expected. This is the human-readable spec the gates are written to satisfy.

> **Automated (issue #85).** This manual walk-through is now reproducible as an
> agent-eval: the 11 rows are encoded as the `tlg-*` corpus
> (`evals/fixtures/tlg-*.md` + `evals/expected/tlg-*.json`). Re-run with
> `/agent-eval --skill test-design-advisor` instead of walking the table by hand.
> A deterministic structural guard lives at `tests/repo/eval_tlg_fixtures.bats`.
> This file remains the canonical row-by-row source of truth; the `tlg-*` corpus
> mirrors it one-to-one (row N → `tlg-0N-*`).

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

Walk-through run 2026-06-04 against `knowledge/test-layer-gates.md` + the Step 1b/Step 2 logic in `skills/test-design-advisor/SKILL.md`.

| # | Actual gate(s) | Actual layer(s) | Match? |
|---|----------------|-----------------|--------|
| 1 | none (`—`) | unit | ✓ |
| 2 | A | `↑ E2E` + lower; `→ cd-test-architecture` | ✓ |
| 3 | B | `↑ E2E` (browser = discovery layer) | ✓ |
| 4 | B (negative) | unit (discovery layer; no escalation) | ✓ |
| 5 | C | `↑ E2E` REQUIRED; integration complementary; `→ cd-test-architecture` | ✓ |
| 6 | C (structural) | `↑ E2E` REQUIRED (structural seam) | ✓ |
| 7 | D | unit + approval and/or screenshot (cost surfaced) | ✓ |
| 8 | D (no-ref) | unit + manual; suggest creating a reference | ✓ |
| 9 | redundancy | unit + integration (different failure mode) + recommendation | ✓ |
| 10 | A + B | `↑ E2E` (union, no duplicate; costs listed once) | ✓ |
| 11 | ambiguity | pending answer — assumption stated, asked once (batched), global option, no silent escalation | ✓ |

**Result: 11/11 match.** No gate-wording adjustment required.
