# Plan excerpt: Checkout discounts — Slice 1, Step 1.1

### Slice 1: Apply a discount code

**Files:** `src/checkout/discount.ts`, `test/discount.test.ts`

```gherkin
Feature: Discount codes at checkout

  Scenario: Valid code reduces the total
    # Still passes if: the discount is rounded half-down instead of half-up
    Given a cart totalling 80.00
    And discount code "AUTUMN15" for 15% that expires 2026-11-30
    When the shopper applies "AUTUMN15" on 2026-11-14
    Then the cart total is 68.00

  Scenario: Expired code is rejected
    # Still passes if: the expired code is also logged
    Given a cart totalling 80.00
    And discount code "SUMMER10" for 10% that expired 2026-08-31
    When the shopper applies "SUMMER10" on 2026-11-14
    Then the code is rejected with message "Discount code expired"
    And the cart total is 80.00
```

#### Step 1.1: `applyDiscount`

**Complexity**: standard
**IMPLEMENT**: `applyDiscount(cart, code, today)` returning the new cart or a rejection
**TEST**: One test per scenario
**REFACTOR**: Extract percent math into `percentOf`
**Files**: `src/checkout/discount.ts`, `test/discount.test.ts`
**Acceptance criteria for this step**:
- AC1.1: A code valid on `today` reduces the cart total by its percentage, rounded to cents.
- AC1.2: A code whose expiry date is before `today` is rejected with the message "Discount code expired" and the total is unchanged.
