# System test design: orders

## Scope

- Mode: --e2e-only
- orders: named
- billing: named
- inventory: named
- Alias map: none
- External boundaries: none
- Commit: abc1234

## System map

orders calls billing over HTTP and reads stock from inventory. observed: orders/src/client.py:12.

## Entangled workflows

No findings.

## Current test architecture

| Suite | Path | Test type | Evidence for the type | Band | Pipeline stage | Blocks merge or deploy |
|---|---|---|---|---|---|---|
| unit | orders/tests/unit | unit | no I/O, observed | in band | pre-merge | yes |

## Test-double validation

No findings.

## Existing E2E triage

No findings.

## Minimum E2E set

No findings.

## Recommended E2E candidates

No findings.

## Rejected candidates

No findings.

## Contract-test findings

No findings.

## Open questions

No findings.

Recommendations only; no tests were changed.
