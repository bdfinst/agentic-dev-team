# Plan: Dunning reminders for overdue invoices

**Created**: 2026-11-05
**Branch**: feat/dunning-reminders
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

Customers with overdue invoices get no reminder today; finance chases them by
hand. Send an automatic reminder email at 7, 14, and 30 days overdue.

## Acceptance Criteria

- [ ] AC1: A customer whose invoice is exactly 7, 14, or 30 days overdue receives one reminder email for that milestone.
- [ ] AC2: A customer never receives the same milestone reminder twice for the same invoice.
- [ ] AC3: An invoice paid in full receives no reminder.

## Slices

### Slice 1: Dunning service

**Depends-on:** none
**Files:** `billing/services/dunning.py`, `tests/billing/test_dunning.py`

**Behavior:**

```gherkin
Feature: Dunning reminders

  Scenario: Seven-day reminder
    # Still passes if: the reminder email subject omits the invoice number
    Given invoice "INV-9" for customer "c-1" is 7 days overdue with no reminders sent
    When the daily dunning run executes
    Then customer "c-1" receives a "7-day" reminder for "INV-9"

  Scenario: Milestone not repeated
    # Still passes if: the 14-day reminder uses the 7-day template
    Given invoice "INV-9" is 7 days overdue and its "7-day" reminder was sent
    When the daily dunning run executes again the same day
    Then customer "c-1" receives no reminder

  Scenario: Paid invoice
    # Still passes if: partially paid invoices are also skipped
    Given invoice "INV-9" is 7 days past due and paid in full
    When the daily dunning run executes
    Then customer "c-1" receives no reminder
```

**Steps:**

#### Step 1.1: Select invoices at a milestone

**Complexity**: standard
**IMPLEMENT**: In `billing/services/dunning.py`, add `DunningService.run(today)`. It opens its own connection with `psycopg.connect(settings.DATABASE_URL)` and runs `SELECT ... FROM invoices WHERE due_date IN (...) AND balance > 0` directly, so the service does not need a new repository method.
**TEST**: Run against the test database seeded with invoices at 6, 7, 14, 30 days overdue; assert the 7/14/30 ones are selected
**REFACTOR**: Extract the milestone list into a constant
**Files**: `billing/services/dunning.py`, `tests/billing/test_dunning.py`
**Covers**: AC1, AC3
**Commit**: `feat(billing): select invoices at dunning milestones`

#### Step 1.2: Send and record reminders

**Complexity**: standard
**IMPLEMENT**: For each selected invoice, build the email body and send it with `smtplib.SMTP(settings.SMTP_HOST).send_message(...)` inside `DunningService.run`; insert a row into `dunning_log` with the same connection
**TEST**: Point `SMTP_HOST` at a local debugging SMTP server and assert one message per milestone; re-run and assert no second message
**REFACTOR**: Move the email body into a template string
**Files**: `billing/services/dunning.py`, `tests/billing/test_dunning.py`
**Covers**: AC1, AC2
**Commit**: `feat(billing): send and record dunning reminders`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |

## Pre-PR Quality Gate

- [ ] All tests pass
- [ ] `/code-review` passes

## Risks & Open Questions

- The SMTP relay rate-limits at 100 messages per minute.
