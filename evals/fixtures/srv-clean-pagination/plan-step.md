# Plan excerpt: Invoice history — Slice 1, Step 1.2

### Slice 1: Paginated invoice history

**Files:** `billing/history.py`, `tests/test_history_pagination.py`

```gherkin
Feature: Paginated invoice history

  Scenario: First page is newest first
    # Still passes if: page 2 repeats the last item of page 1
    Given customer "c-1" has 3 invoices created on Nov 1, Nov 2, and Nov 3
    When page 1 with page size 2 is requested
    Then the invoices are Nov 3 then Nov 2
    And more pages are available

  Scenario: Page past the end is empty
    # Still passes if: the total count is not returned
    Given customer "c-1" has 3 invoices
    When page 3 with page size 2 is requested
    Then no invoices are returned
    And no more pages are available

  Scenario: Oversized page is refused
    # Still passes if: the error message wording changes
    When page 1 with page size 101 is requested
    Then the request fails with a ValueError
```

#### Step 1.2: `list_invoices` pagination

**Complexity**: standard
**IMPLEMENT**: `list_invoices(repo, customer_id, page, page_size)` returning `Page(items, has_more)`
**TEST**: One test per scenario
**REFACTOR**: Name the cap `MAX_PAGE_SIZE`
**Files**: `billing/history.py`, `tests/test_history_pagination.py`
**Acceptance criteria for this step**:
- AC1.2a: Items are ordered by `created_at` descending; page `n` holds items `(n-1)*page_size` to `n*page_size - 1`.
- AC1.2b: `has_more` is true only when items exist after the returned page.
- AC1.2c: `page_size` above 100 or below 1, or `page` below 1, raises `ValueError`.
