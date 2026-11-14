# Plan: Coupon redemption limits

**Created**: 2026-11-03
**Branch**: feat/coupon-limits
**Status**: draft
**Gherkin persistence**: features/

## Goal

Marketing runs coupons with a fixed number of uses, but the checkout service
redeems a coupon any number of times. Last month one 100-use coupon was redeemed
1,912 times. Enforce a per-coupon redemption cap and a once-per-customer rule at
checkout.

## Acceptance Criteria

- [ ] AC1: A coupon with `max_redemptions = N` is accepted for the first N successful checkouts and rejected for checkout N+1 with error code `COUPON_EXHAUSTED`.
- [ ] AC2: A customer who has already redeemed a coupon is rejected with error code `COUPON_ALREADY_USED` on a second checkout with the same coupon.
- [ ] AC3: A rejected coupon leaves the cart total unchanged and does not count as a redemption.
- [ ] AC4: A coupon with `max_redemptions = null` has no cap.

## Slices

### Slice 1: Redemption cap

**Depends-on:** none
**Files:** `checkout/coupons.py`, `checkout/tests/test_coupon_cap.py`

**Behavior:**

```gherkin
Feature: Coupon redemption cap

  Scenario: Last available use is accepted
    # Still passes if: the discount amount is computed from the pre-tax total
    Given coupon "SPRING10" with a cap of 2 and 1 recorded redemption
    When a customer checks out with "SPRING10"
    Then the checkout succeeds
    And "SPRING10" has 2 recorded redemptions

  Scenario: Exhausted coupon is rejected
    Given coupon "SPRING10" with a cap of 2 and 2 recorded redemptions
    When a customer checks out with "SPRING10"
    Then the checkout is rejected with error code "COUPON_EXHAUSTED"
    And the cart total is unchanged
    And "SPRING10" has 2 recorded redemptions

  Scenario: Uncapped coupon
    # Still passes if: the coupon lookup returns any non-null result
    Given coupon "WELCOME" with no cap and 5000 recorded redemptions
    When a customer checks out with "WELCOME"
    Then the response is not empty
```

**Steps:**

#### Step 1.1: Enforce the cap

**Complexity**: standard
**IMPLEMENT**: In `apply_coupon`, compare recorded redemptions to `max_redemptions`; raise `CouponRejected("COUPON_EXHAUSTED")` at the cap
**TEST**: Cap of 2: second use accepted, third rejected; total unchanged on reject; null cap accepted
**REFACTOR**: Name the comparison `is_exhausted(coupon)`
**Files**: `checkout/coupons.py`, `checkout/tests/test_coupon_cap.py`
**Covers**: AC1, AC3, AC4
**Commit**: `feat(checkout): enforce coupon redemption cap`

#### Step 1.2: Cache coupon lookups

**Complexity**: standard
**IMPLEMENT**: Wrap `load_coupon(code)` in a 60-second in-process LRU cache
**TEST**: Second lookup within 60s does not hit the store
**REFACTOR**: Move cache TTL to settings
**Files**: `checkout/coupons.py`, `checkout/tests/test_coupon_cap.py`
**Commit**: `perf(checkout): cache coupon lookups`

### Slice 2: Once per customer

**Depends-on:** 1
**Files:** `checkout/coupons.py`, `checkout/tests/test_coupon_per_customer.py`

**Behavior:**

```gherkin
Feature: Once-per-customer coupons

  Scenario: Second use by the same customer is rejected
    # Still passes if: the first redemption is not recorded at all
    Given customer "ana" has already redeemed coupon "SPRING10"
    When "ana" checks out with "SPRING10"
    Then the checkout is rejected with error code "COUPON_ALREADY_USED"
    And the cart total is unchanged
```

**Steps:**

#### Step 2.1: Reject repeat redemptions

**Complexity**: standard
**IMPLEMENT**: Look up prior redemptions by (customer, coupon) before applying
**TEST**: Repeat redemption raises `CouponRejected("COUPON_ALREADY_USED")`; a different customer is accepted
**REFACTOR**: Share the rejection path with the cap check
**Files**: `checkout/coupons.py`, `checkout/tests/test_coupon_per_customer.py`
**Covers**: AC2, AC3
**Commit**: `feat(checkout): reject repeat coupon redemption per customer`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |
| 2 | 2 |

## Pre-PR Quality Gate

- [ ] All tests pass
- [ ] `/code-review` passes

## Risks & Open Questions

- Concurrent checkouts at the cap boundary may both succeed; a row lock is out of scope for this plan.
