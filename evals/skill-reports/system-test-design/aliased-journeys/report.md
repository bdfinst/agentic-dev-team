# System test design: orders

## Scope

- Mode: full
- orders: named
- checkout-svc: named
- Alias map: none
- External boundaries: none
- Commit: abc1234
- Alias map: orders = checkout-svc (same deployable under two names)

## System map

No findings.

## Entangled workflows

No findings.

## Current test architecture

No findings.

## Test-double validation

No findings.

## Existing E2E triage

No findings.

## Minimum E2E set

1. Place an order and see it billed. Provenance: orders/e2e/test_place.py, checkout-svc/e2e/test_place.py (listed once).
2. Cancel an order. Provenance: orders. possibly same as: Refund an order (checkout-svc); component sets only partly overlap.
3. Refund an order. Provenance: checkout-svc. possibly same as: Cancel an order.

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
