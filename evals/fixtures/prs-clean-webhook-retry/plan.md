# Plan: Retry failed outbound webhooks

**Created**: 2026-11-12
**Branch**: feat/webhook-retry
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

Outbound webhooks are sent once. Over the last 30 days 2.1% of deliveries
(about 1,800) failed with a 5xx or timeout from the receiver and were never
retried; 14 merchants opened tickets about missed order events. Retry
transient failures with backoff so a brief receiver outage does not lose
events.

Alternative considered: the queue's built-in redelivery. Rejected because it
retries every failure, including permanent 4xx responses, and gives no
per-endpoint cap. The existing `retry_with_backoff` helper in `common/retry.py`
is reused instead of a new library.

## Acceptance Criteria

- [ ] AC1: A delivery that gets a 5xx or a 10-second timeout is retried up to 4 more times at 1, 5, 25, and 125 seconds.
- [ ] AC2: A delivery that gets a 4xx is not retried.
- [ ] AC3: After the last failed retry, the delivery is marked `failed` and shown in the existing failed-deliveries report.
- [ ] AC4: Retries are off unless the `webhook_retries` flag is on for the merchant.

## Out of scope

- Manual "resend" from the dashboard (separate request, not yet prioritized).
- Changing the webhook payload or signature.

## Slices

### Slice 1: Retry transient failures behind a flag

**Depends-on:** none
**Files:** `webhooks/deliver.py`, `tests/webhooks/test_retry.py`

**Behavior:**

```gherkin
Feature: Webhook retry

  Scenario: Transient failure is retried
    # Still passes if: the backoff intervals are 2, 10, 50, 250 seconds
    Given merchant "m-1" has webhook retries on
    And its endpoint fails with 503 once and then returns 200
    When an order event is delivered to "m-1"
    Then the endpoint receives the event twice and the delivery is "succeeded"

  Scenario: Permanent failure is not retried
    # Still passes if: the 4xx body is not logged
    Given merchant "m-1" has webhook retries on
    And its endpoint returns 410
    When an order event is delivered to "m-1"
    Then the endpoint receives the event once and the delivery is "failed"

  Scenario: Flag off keeps today's behavior
    # Still passes if: the failure reason text changes
    Given merchant "m-2" has webhook retries off
    And its endpoint returns 503
    When an order event is delivered to "m-2"
    Then the endpoint receives the event once and the delivery is "failed"
```

**Steps:**

#### Step 1.1: Classify responses and retry behind the flag

**Complexity**: standard
**IMPLEMENT**: In `deliver`, wrap the send in `retry_with_backoff` for 5xx/timeouts when the flag is on
**TEST**: Fake endpoint and fake clock; assert attempt counts and final status for 503-then-200, 410, and flag off
**REFACTOR**: Name the transient-status check `is_transient(response)`
**Files**: `webhooks/deliver.py`, `tests/webhooks/test_retry.py`
**Covers**: AC1, AC2, AC3, AC4
**Commit**: `feat(webhooks): retry transient delivery failures`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |

## Rollout and rollback

Enable the flag for 5 merchants for one week, then all. Rollback is turning
the flag off; no schema or payload change ships.

## Risks & Open Questions

- Retries add up to about 156 seconds of extra worker time per failing delivery; at today's failure rate that is under 1% more worker load.
