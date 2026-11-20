# System test design: orders

## Scope

- Mode: --overlap-only
- orders: named
- Alias map: none
- External boundaries: none
- Commit: abc1234
- Evidence: orders mutation (mutmut) from evidence/mutmut-stats.json

## Current test architecture

No findings.

## Test-double validation

No findings.

## Overlap and misplacement

| Test | Behavior | Also asserted by | Owning type | Action |
|---|---|---|---|---|
| tests/unit/test_pricing.py::test_discount | apply_discount gold tier | tests/component/test_pricing_api.py::test_discount | unit | remove the assertion from the component test |

### Layer overlap (trim, not remove)

- [evidence: coverage-backed; evidence-confidence: medium; basis: mutmut records both tests reaching apply_discount (function-level reach; mutmut does not record which test killed a mutant)] Cross-Layer Overlap | tests/unit/test_pricing.py::test_discount + tests/component/test_pricing_api.py::test_discount | keep the unit test; trim the component test to seam assertions

## Contract-test findings

No findings.

## Test improvements

No findings.

## Open questions

No findings.

Recommendations only; no tests were changed.
