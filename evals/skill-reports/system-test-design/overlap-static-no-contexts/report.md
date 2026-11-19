# System test design: orders

## Scope

- Mode: --overlap-only
- orders: named
- Alias map: none
- External boundaries: none
- Commit: abc1234
- Evidence: orders coverage path evidence/coverage.json unusable (no contexts)

## Current test architecture

No findings.

## Test-double validation

No findings.

## Overlap and misplacement

| Test | Behavior | Also asserted by | Owning type | Action |
|---|---|---|---|---|
| tests/unit/test_pricing.py::test_discount | apply_discount gold tier | tests/component/test_pricing_api.py::test_discount | unit | remove the assertion from the component test |

- [evidence: static-judgment; evidence-confidence: low; basis: no contexts] Cross-Layer Overlap | tests/unit/test_pricing.py::test_discount + tests/component/test_pricing_api.py::test_discount | severity suggestion; candidate; confirm with coverage before trimming

## Contract-test findings

No findings.

## Test improvements

No findings.

## Open questions

No findings.

Recommendations only; no tests were changed.
