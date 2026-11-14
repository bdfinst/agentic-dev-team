# Plan: Unify subscription status values

**Created**: 2026-11-11
**Branch**: feat/subscription-state
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

Subscriptions carry two status columns: `status` (`active`, `paused`,
`cancelled`) and `legacy_status` (free text from the 2022 import). Billing and
support disagree on which one wins, and in October 37 customers were charged
while `legacy_status` read "cancelled". Make one canonical field the only source
of truth.

## Acceptance Criteria

- [ ] AC1: The `subscriptions` table has a single `state` column with values `active`, `paused`, `cancelled`, `past_due`; every row maps from its old values by the table in Step 1.1.
- [ ] AC2: The public REST API (`GET /v1/subscriptions/{id}`, used by the mobile apps and three partner integrations) returns `state` in place of `status`.
- [ ] AC3: Billing charges only subscriptions whose `state` is `active` or `past_due`.

## Out of scope

- Changing how pauses are scheduled.
- The admin UI (it reads through the same API).

## Slices

### Slice 1: Canonical state

**Depends-on:** none
**Files:** `db/migrations/2026_11_11_subscription_state.sql`, `subscriptions/model.py`, `subscriptions/api.py`, `billing/charge_run.py`, `tests/`

**Behavior:**

```gherkin
Feature: Canonical subscription state

  Scenario: Legacy cancelled maps to cancelled
    # Still passes if: "paused" rows are mapped to "active"
    Given a subscription with status "active" and legacy_status "cancelled"
    When the migration runs
    Then the subscription's state is "cancelled"

  Scenario: API exposes state
    # Still passes if: the response also includes an unrelated "plan" field
    Given a subscription with state "paused"
    When a client fetches it through the public API
    Then the response field "state" is "paused" and there is no "status" field

  Scenario: Billing skips cancelled
    # Still passes if: past_due subscriptions are charged twice a month
    Given a subscription with state "cancelled"
    When the charge run executes
    Then no charge is created for it
```

**Steps:**

#### Step 1.1: Migration

**Complexity**: complex
**IMPLEMENT**: One migration that adds `state`, backfills it (legacy "cancelled"/"canceled" wins over `status`; legacy "late" maps to `past_due`), then drops `status` and `legacy_status`
**TEST**: Migrate a fixture DB; assert each mapping row
**REFACTOR**: Move the mapping into a SQL CASE table
**Files**: `db/migrations/2026_11_11_subscription_state.sql`, `tests/db/test_state_migration.py`
**Covers**: AC1
**Commit**: `feat(db): collapse subscription status into state`

#### Step 1.2: Model, API, and billing switch to `state`

**Complexity**: complex
**IMPLEMENT**: Rename the field in the model and serializer; billing filters on `state`. Ships in the same deploy as Step 1.1.
**TEST**: API contract test for `state`; billing test for each state
**REFACTOR**: Remove the dead `status` helpers
**Files**: `subscriptions/model.py`, `subscriptions/api.py`, `billing/charge_run.py`, `tests/`
**Covers**: AC2, AC3
**Commit**: `feat(subscriptions): expose state in API and billing`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |

## Risks & Open Questions

- Whether `past_due` subscriptions are charged is awaiting a decision from the Payments team; their answer may change AC3 and the mapping table.
- Partner integrations have not been told about the field rename yet.
