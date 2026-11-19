# System test design: orders

## Scope

- Mode: full
- orders: named
- checkout-svc: named
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

| Test | Class | Reason | Target layer and covering test |
|---|---|---|---|
| orders/e2e/test_place.py::test_place | KEEP | category: critical business flow across two real services | stage: post-deploy |
| checkout-svc/e2e/test_place.py::test_place | KEEP | same journey under an alias | stage: post-deploy |
| orders/e2e/test_cancel.py::test_cancel | KEEP | category: async handoff | stage: scheduled |
| checkout-svc/e2e/test_refund.py::test_refund | KEEP | category: async handoff | stage: scheduled |

## Minimum E2E set

1. Place an order and see it billed. Provenance: orders/e2e/test_place.py, checkout-svc/e2e/test_place.py (listed once). Stage: post-deploy.
2. Cancel an order. Provenance: orders/e2e/test_cancel.py. Stage: scheduled. possibly same as: Refund an order (checkout-svc); component sets only partly overlap.
3. Refund an order. Provenance: checkout-svc/e2e/test_refund.py. Stage: scheduled. possibly same as: Cancel an order.

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
