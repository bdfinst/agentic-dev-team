# Plan: Stock release on order cancellation

**Created**: 2026-11-07
**Branch**: feat/stock-release
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

When an order is cancelled, its reserved stock stays reserved, so items show as
out of stock while sitting on the shelf. Release the reserved quantity back to
`on_hand` when an order line is cancelled.

## Acceptance Criteria

- [ ] AC1: Cancelling a line for SKU S with quantity Q increases S's `on_hand` by exactly Q.
- [ ] AC2: Cancelling a line for an unknown SKU raises `UnknownSku` and changes no stock.
- [ ] AC3: A non-positive quantity raises `ValueError` and changes no stock.

## Slices

### Slice 1: Release stock

**Depends-on:** none
**Files:** `inventory/model.py`, `inventory/services/reservations.py`, `tests/inventory/test_release.py`

**Behavior:**

```gherkin
Feature: Release reserved stock

  Scenario: Cancelled line returns stock
    # Still passes if: the release is not logged
    Given SKU "MUG-01" has 4 on hand
    When a cancelled line releases 3 of "MUG-01"
    Then "MUG-01" has 7 on hand

  Scenario: Unknown SKU
    # Still passes if: the exception message omits the SKU
    Given no SKU "NOPE-9" exists
    When a cancelled line releases 1 of "NOPE-9"
    Then the release fails with "UnknownSku"

  Scenario: Non-positive quantity
    # Still passes if: zero and negative quantities share one error message
    Given SKU "MUG-01" has 4 on hand
    When a cancelled line releases 0 of "MUG-01"
    Then the release fails with "ValueError"
    And "MUG-01" has 4 on hand
```

**Steps:**

#### Step 1.1: `StockItem.release`

**Complexity**: standard
**IMPLEMENT**: Add `StockItem.release(qty)` beside `reserve`, raising `ValueError` for `qty <= 0`
**TEST**: Release 3 onto 4 gives 7; release 0 and -1 raise and leave `on_hand` unchanged
**REFACTOR**: Share the positive-quantity guard between `reserve` and `release`
**Files**: `inventory/model.py`, `tests/inventory/test_release.py`
**Covers**: AC1, AC3
**Commit**: `feat(inventory): add StockItem.release`

#### Step 1.2: `ReservationService.release`

**Complexity**: standard
**IMPLEMENT**: Add `release(sku, qty)` to `ReservationService`, using the injected `StockRepository` exactly as `reserve` does (get, mutate, save; `UnknownSku` when missing)
**TEST**: In-memory `StockRepository` fake; assert saved `on_hand`, and that an unknown SKU raises and saves nothing
**REFACTOR**: Extract `_load(sku)` shared by `reserve` and `release`
**Files**: `inventory/services/reservations.py`, `tests/inventory/test_release.py`
**Covers**: AC1, AC2
**Commit**: `feat(inventory): release stock on cancellation`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |

## Pre-PR Quality Gate

- [ ] All tests pass
- [ ] `/code-review` passes

## Risks & Open Questions

- Wiring the cancellation event to `release` is a separate plan owned by the orders team.
