# System test design: orders

## Scope

- Mode: full
- orders: named
- billing: named
- Alias map: none
- External boundaries: none
- Commit: abc1234

## System map

No findings.

## Entangled workflows

| Workflow | Kind | Deployables | Evidence | Guarding E2E | Decoupling step |
|---|---|---|---|---|---|
| Invoice totals | shared table or schema | orders, billing | orders/db/models.py:8 and billing/db/models.py:5 both map table `invoice_lines` (observed) | Candidate 1 (temporary) | billing owns `invoice_lines` and exposes it through an API; add a contract test at the boundary |

## Current test architecture

No findings.

## Test-double validation

No findings.

## Existing E2E triage

No findings.

## Minimum E2E set

No findings.

## Recommended E2E candidates

### Candidate 1
- Type: entangled workflow (Invoice totals); temporary
- Flow: order placed, invoice read
- Failure it detects: a row written by orders that billing reads with another meaning; no other type sees both deployables
- Assert: the invoice total matches the order lines
- Do not assert: discount math (owned by the orders unit tests)
- Placement: post-deploy, because it needs both real deployables
- Environment and test data: ephemeral environment; the test creates and removes its own rows
- Async handling: poll for the invoice, bounded wait
- Evidence: observed

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
