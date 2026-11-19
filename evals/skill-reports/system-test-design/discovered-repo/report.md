# System test design: orders

## Scope

- Mode: full
- orders: named
- billing: discovered (repowise index)
- shipping: not scanned (no index, no path)
- Alias map: none
- External boundaries: none
- Commit: abc1234

## System map

orders references billing and shipping. observed: orders/config.yaml:1-2.

## Entangled workflows

No findings.

## Current test architecture

No findings.

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

## Overlap and misplacement

No findings.

## Contract-test findings

No findings.

## Test improvements

No findings.

## Open questions

No findings.

Recommendations only; no tests were changed.
