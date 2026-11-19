# System test design: orders

## Scope

- Mode: --overlap-only
- orders: named
- billing: named
- Alias map: none
- External boundaries: none
- Commit: abc1234
- Evidence: coverage for orders only (coveragepy-json); billing had none.

## Current test architecture

No findings.

## Test-double validation

No findings.

## Overlap and misplacement

| Test | Behavior | Also asserted by | Owning type | Action |
|---|---|---|---|---|
| orders tests/unit/test_pricing.py::test_discount | apply_discount | orders tests/component/test_pricing_api.py::test_discount | unit | trim the component test |
| billing tests/unit/test_ledger.py::test_post | post | billing tests/component/test_ledger_api.py::test_post | unit | trim the component test |

### Layer overlap (trim, not remove)

- [evidence: coverage-backed; evidence-confidence: high; basis: shared covered line 3 inside apply_discount] Cross-Layer Overlap | tests/unit/test_pricing.py::test_discount + tests/component/test_pricing_api.py::test_discount | keep the unit test; trim the component test to seam assertions
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_ledger.py::test_post + tests/component/test_ledger_api.py::test_post | severity suggestion; candidate; confirm with coverage before trimming

## Contract-test findings

No findings.

## Test improvements

No findings.

## Open questions

No findings.

Recommendations only; no tests were changed.
