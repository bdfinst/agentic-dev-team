# System test design: orders

## Scope

- Mode: full
- orders: named
- Alias map: none
- External boundaries: none
- Commit: abc1234

## System map

No findings.

## Entangled workflows

No findings.

## Current test architecture

No findings.

## Test-double validation

No findings.

## Existing E2E triage

| Test | Class | Reason | Target layer and covering test |
|---|---|---|---|
| e2e/test_validation.py::test_rejects_empty_cart | DELETE | asserts only a validation error | unit: tests/unit/test_cart.py::test_rejects_empty_cart already asserts it |
| e2e/test_validation.py::test_rejects_bad_sku | PUSH DOWN -> unit | asserts only a validation error | unit: none found, create one first |

## Minimum E2E set

No findings.

## Recommended E2E candidates

No findings.

## Rejected candidates

No findings.

## Overlap and misplacement

No findings.

## Contract-test findings

No findings.

## Test improvements

No findings.

## Open questions

No findings.

Recommendations only; no tests were changed.
