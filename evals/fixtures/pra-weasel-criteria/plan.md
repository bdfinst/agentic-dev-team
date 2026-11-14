# Plan: Order history CSV export

**Created**: 2026-11-02
**Branch**: feat/order-csv-export
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

Store owners ask support for spreadsheets of their order history about 40 times
a week. Add a "Download CSV" endpoint so owners can export their own orders
without a support ticket.

## Acceptance Criteria

- [ ] AC1: `GET /stores/{id}/orders.csv` returns `text/csv` with one header row and one row per order, columns `order_id,placed_at,total,status`.
- [ ] AC2: The export handles large order histories appropriately.
- [ ] AC3: A user who does not own the store receives HTTP 403 and no CSV body.
- [ ] AC4: A date range filter (`from`, `to`, ISO dates, inclusive) limits the rows to orders placed in that range.

## Slices

### Slice 1: Basic export

**Depends-on:** none
**Files:** `app/exports/orders_csv.py`, `app/routes/orders.py`, `tests/exports/test_orders_csv.py`

**Behavior:**

```gherkin
Feature: Order history CSV export

  Scenario: Owner downloads all orders
    # Still passes if: the status column is written in upper case
    Given store "Acme Mugs" owned by "dana" has 3 orders
    When "dana" requests the orders CSV for "Acme Mugs"
    Then the response content type is "text/csv"
    And the CSV has a header row "order_id,placed_at,total,status"
    And the CSV has 3 data rows

  Scenario: Non-owner is refused
    # Still passes if: the 403 response carries a JSON error body
    Given store "Acme Mugs" owned by "dana"
    When "lee" requests the orders CSV for "Acme Mugs"
    Then the response status is 403
    And no CSV rows are returned
```

**Steps:**

#### Step 1.1: Serialize orders to CSV

**Complexity**: standard
**IMPLEMENT**: Write `orders_to_csv(orders)` that emits the header and one row per order
**TEST**: Assert header text and row count for 0 and 3 orders
**REFACTOR**: Extract column list into a constant
**Files**: `app/exports/orders_csv.py`, `tests/exports/test_orders_csv.py`
**Covers**: AC1
**Commit**: `feat(exports): serialize orders to CSV`

#### Step 1.2: Route with ownership check

**Complexity**: standard
**IMPLEMENT**: Add the `orders.csv` route; reject non-owners with 403
**TEST**: Owner gets 200 + CSV; non-owner gets 403 and empty body
**REFACTOR**: Reuse the existing `require_store_owner` guard
**Files**: `app/routes/orders.py`, `tests/exports/test_orders_csv.py`
**Covers**: AC1, AC3
**Commit**: `feat(routes): add orders CSV export route`

### Slice 2: Date range filter

**Depends-on:** 1
**Files:** `app/exports/orders_csv.py`, `tests/exports/test_orders_csv.py`

**Steps:**

#### Step 2.1: Filter by from/to

**Complexity**: standard
**IMPLEMENT**: Parse `from`/`to` query params and filter orders by `placed_at`
**TEST**: Test that the filter works
**REFACTOR**: Move date parsing into a helper
**Files**: `app/exports/orders_csv.py`, `tests/exports/test_orders_csv.py`
**Covers**: AC4
**Commit**: `feat(exports): filter CSV export by date range`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |
| 2 | 2 |

## Pre-PR Quality Gate

- [ ] All tests pass
- [ ] Linter passes
- [ ] `/code-review` passes

## Risks & Open Questions

- Very large stores (50k+ orders) may need streaming; not measured yet.
