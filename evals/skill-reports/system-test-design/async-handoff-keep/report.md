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

No findings.

## Current test architecture

No findings.

## Test-double validation

No findings.

## Existing E2E triage

| Test | Class | Reason | Target layer and covering test |
|---|---|---|---|
| e2e/test_handoff.py::test_order_reaches_billing | KEEP | category: async handoff across two real services; no component, contract, or resilience test asserts the outcome for this service pair | stage: post-deploy or scheduled |

## Minimum E2E set

Order reaches billing (async handoff). Provenance: orders/e2e/test_handoff.py.

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
