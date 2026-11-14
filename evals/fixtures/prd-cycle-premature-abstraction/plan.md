# Plan: Weekly order digest email

**Created**: 2026-11-06
**Branch**: feat/order-digest
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

Customers who place several small orders a week ask for one summary instead of
many receipts. Send an opt-in weekly digest email listing the past 7 days of
orders.

## Acceptance Criteria

- [ ] AC1: A customer with digest enabled and at least one order in the past 7 days receives one email listing each order id and total.
- [ ] AC2: A customer with digest enabled and no orders in the past 7 days receives no email.
- [ ] AC3: A customer with digest disabled receives no email.

## Slices

### Slice 1: Weekly digest

**Depends-on:** none
**Files:** `src/notifications/digest.ts`, `src/notifications/digest-strategy.ts`, `src/notifications/dispatcher.ts`, `src/notifications/digest.test.ts`

**Behavior:**

```gherkin
Feature: Weekly order digest

  Scenario: Digest lists the week's orders
    # Still passes if: orders are listed newest first instead of oldest first
    Given customer "c-7" has digest enabled and orders "O-1" and "O-2" in the past 7 days
    When the weekly digest runs
    Then "c-7" receives one digest email listing "O-1" and "O-2" with their totals

  Scenario: No orders, no email
    # Still passes if: the digest subject line changes
    Given customer "c-7" has digest enabled and no orders in the past 7 days
    When the weekly digest runs
    Then "c-7" receives no email

  Scenario: Digest disabled
    # Still passes if: disabled customers are still queried for orders
    Given customer "c-8" has digest disabled and order "O-3" in the past 7 days
    When the weekly digest runs
    Then "c-8" receives no email
```

**Steps:**

#### Step 1.1: Digest strategy abstraction

**Complexity**: complex
**IMPLEMENT**: Add `src/notifications/digest-strategy.ts` with `abstract class AbstractDigestStrategy`, a `DigestStrategyFactory` that picks a strategy by channel name, and one concrete `EmailDigestStrategy`. Email is the only channel planned now or on the roadmap.
**TEST**: Factory returns `EmailDigestStrategy` for `"email"` and throws for unknown names
**REFACTOR**: Move channel names into an enum
**Files**: `src/notifications/digest-strategy.ts`, `src/notifications/digest.test.ts`
**Covers**: AC1
**Commit**: `feat(notifications): add digest strategy abstraction`

#### Step 1.2: Build the digest from orders

**Complexity**: standard
**IMPLEMENT**: In `src/notifications/digest.ts`, `import { OrderService } from "../orders/service"`, construct it, and call `listForCustomer(customerId, sevenDaysAgo)`; skip customers with no orders or digest disabled; send via the strategy
**TEST**: Fake repository behind `OrderService`; assert one email for c-7, none for empty or disabled customers
**REFACTOR**: Extract the date window into `lastSevenDays(now)`
**Files**: `src/notifications/digest.ts`, `src/notifications/digest.test.ts`
**Covers**: AC1, AC2, AC3
**Commit**: `feat(notifications): build weekly order digest`

#### Step 1.3: Register the digest with the dispatcher

**Complexity**: standard
**IMPLEMENT**: In `src/notifications/dispatcher.ts`, `import { sendDigest } from "./digest"` and add a `"weekly-digest"` event kind that calls it
**TEST**: Dispatching `weekly-digest` calls `sendDigest` once
**REFACTOR**: None needed beyond formatting
**Files**: `src/notifications/dispatcher.ts`, `src/notifications/digest.test.ts`
**Covers**: AC1
**Commit**: `feat(notifications): dispatch weekly digest`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |

## Pre-PR Quality Gate

- [ ] All tests pass
- [ ] Type check passes
- [ ] `/code-review` passes
