# System test design: orders

## Scope

- Mode: --overlap-only
- orders: named
- Alias map: none
- External boundaries: none
- Commit: abc1234
- Evidence: orders coverage (istanbul-dir) from evidence/coverage

## Current test architecture

No findings.

## Test-double validation

No findings.

## Overlap and misplacement

| Test | Behavior | Also asserted by | Owning type | Action |
|---|---|---|---|---|
| tests/unit/pricing.test.js::discount | applyDiscount gold tier | tests/component/pricing.api.test.js::discount | unit | remove the assertion from the component test |

- [evidence: coverage-backed; evidence-confidence: high; basis: shared covered line 2 inside applyDiscount] Cross-Layer Overlap | tests/unit/pricing.test.js::discount + tests/component/pricing.api.test.js::discount | keep the unit test; trim the component test to seam assertions

## Contract-test findings

No findings.

## Test improvements

No findings.

## Open questions

No findings.

Recommendations only; no tests were changed.
