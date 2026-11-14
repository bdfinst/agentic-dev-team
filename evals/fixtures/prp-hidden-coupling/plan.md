# Plan: Shipment tracking

**Created**: 2026-11-09
**Branch**: feat/shipment-tracking
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

"Where is my parcel?" is 30% of support tickets. Record carrier updates, email
customers when an order ships, show a tracking page, and list shipments for support.

## Acceptance Criteria

- [ ] AC1: A carrier webhook with status `shipped` records a shipment and publishes an `OrderShipped` event carrying `orderId`, `carrier`, and `trackingNumber`.
- [ ] AC2: On `OrderShipped`, the customer receives one email containing the tracking number.
- [ ] AC3: `/track/:orderId` shows the latest carrier status for the order owner.
- [ ] AC4: `/admin/shipments` lists shipments newest first for support staff.

## Slices

### Slice 1: Record shipments and publish OrderShipped

**Depends-on:** none
**Files:** `src/shipping/carrier_webhook.ts`, `src/events/order_shipped.ts`, `migrations/0042_create_shipments.sql`, `src/shipping/carrier_webhook.test.ts`

**Behavior:**

```gherkin
Feature: Carrier shipment updates

  Scenario: Shipped webhook publishes OrderShipped
    # Still passes if: the webhook response body changes
    Given order "O-5" awaiting shipment
    When the carrier reports "O-5" shipped with tracking number "1Z999"
    Then an OrderShipped event for "O-5" with tracking number "1Z999" is published
```

**Steps:**

#### Step 1.1: Shipments table, event type, webhook

**Complexity**: standard
**IMPLEMENT**: Migration `0042_create_shipments.sql`; define and export the `OrderShipped` type and `onOrderShipped(handler)` subscriber in `src/events/order_shipped.ts`; publish from the webhook
**TEST**: Post a `shipped` webhook; assert the row and the published event
**REFACTOR**: Extract webhook signature check
**Files**: `src/shipping/carrier_webhook.ts`, `src/events/order_shipped.ts`, `migrations/0042_create_shipments.sql`, `src/shipping/carrier_webhook.test.ts`
**Covers**: AC1
**Commit**: `feat(shipping): record shipments and publish OrderShipped`

### Slice 2: Shipped email

**Depends-on:** none
**Files:** `src/email/shipped_email.ts`, `src/email/shipped_email.test.ts`

**Behavior:**

```gherkin
Feature: Shipped email

  Scenario: Customer is emailed the tracking number
    # Still passes if: the email subject line changes
    Given order "O-5" belongs to "dana@example.com"
    When order "O-5" ships with tracking number "1Z999"
    Then "dana@example.com" receives one email containing "1Z999"
```

**Steps:**

#### Step 2.1: Subscribe and send

**Complexity**: standard
**IMPLEMENT**: `import { onOrderShipped, OrderShipped } from "../events/order_shipped"`; subscribe and send the shipped template
**TEST**: Emit an `OrderShipped` event; assert one email with the tracking number
**REFACTOR**: Move template name to a constant
**Files**: `src/email/shipped_email.ts`, `src/email/shipped_email.test.ts`
**Covers**: AC2
**Commit**: `feat(email): send shipped email`

### Slice 3: Tracking page

**Depends-on:** none
**Files:** `src/pages/Tracking.tsx`, `src/pages/Tracking.test.tsx`

**Behavior:**

```gherkin
Feature: Tracking page

  Scenario: Owner sees latest status
    # Still passes if: the status timestamp format changes
    Given order "O-5" owned by "dana" has carrier status "in transit"
    When "dana" opens the tracking page for "O-5"
    Then the page shows "in transit"
```

**Steps:**

#### Step 3.1: Tracking page

**Complexity**: standard
**IMPLEMENT**: Add `Tracking.tsx` and register the `/track/:orderId` route in `src/routes.tsx` behind the owner check
**TEST**: Owner sees status; other user is redirected
**REFACTOR**: Extract status badge
**Files**: `src/pages/Tracking.tsx`, `src/pages/Tracking.test.tsx`
**Covers**: AC3
**Commit**: `feat(pages): add tracking page`

### Slice 4: Admin shipments list

**Depends-on:** none
**Files:** `src/pages/admin/Shipments.tsx`, `src/pages/admin/Shipments.test.tsx`, `src/routes.tsx`, `migrations/0042_index_shipments_created_at.sql`

**Behavior:**

```gherkin
Feature: Admin shipments list

  Scenario: Newest first
    # Still passes if: the page size changes from 50 to 25
    Given shipments created at 09:00 and 10:00 today
    When a support user opens the shipments list
    Then the 10:00 shipment is listed first
```

**Steps:**

#### Step 4.1: Admin list and index

**Complexity**: standard
**IMPLEMENT**: Add `Shipments.tsx`, the `/admin/shipments` route in `src/routes.tsx`, and migration `0042_index_shipments_created_at.sql` adding an index on `shipments.created_at`
**TEST**: Seed two shipments; assert order
**REFACTOR**: Share the admin table component
**Files**: `src/pages/admin/Shipments.tsx`, `src/pages/admin/Shipments.test.tsx`, `src/routes.tsx`, `migrations/0042_index_shipments_created_at.sql`
**Covers**: AC4
**Commit**: `feat(admin): list shipments`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1, 2, 3, 4 |

