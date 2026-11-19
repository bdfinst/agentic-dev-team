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

No findings.

## Minimum E2E set

Gap-list items are not in this set.

## Recommended E2E candidates

No findings.

## Rejected candidates

No findings.

## Overlap and misplacement

No findings.

## Contract-test findings

No findings.

## Test improvements

Gap list (capped at 10; 2 more uncovered interactions not shown):

1. orders -> billing interaction 1: no covering test (observed)
2. orders -> billing interaction 2: no covering test (observed)
3. orders -> billing interaction 3: no covering test (observed)
4. orders -> billing interaction 4: no covering test (observed)
5. orders -> billing interaction 5: no covering test (observed)
6. orders -> billing interaction 6: no covering test (observed)
7. orders -> billing interaction 7: no covering test (observed)
8. orders -> billing interaction 8: no covering test (observed)
9. orders -> billing interaction 9: no covering test (observed)
10. orders -> billing interaction 10: no covering test (observed)

Interaction 3: no covering test, and a contract test could pin it. Cover with contract test instead; no E2E proposed.

## Open questions

No findings.

Recommendations only; no tests were changed.
