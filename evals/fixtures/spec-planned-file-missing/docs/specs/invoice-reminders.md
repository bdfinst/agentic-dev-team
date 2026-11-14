# Spec: Invoice reminders

## Acceptance criteria

1. An invoice unpaid 7 days after its due date is marked overdue.
2. Marking an invoice overdue sends one reminder email to the billing contact.
3. A paid invoice is never marked overdue.

## Scenarios

```gherkin
Scenario: Overdue invoice triggers one reminder
  Given an invoice due 8 days ago and unpaid
  When the daily reminder job runs twice
  Then the invoice is overdue and exactly one reminder was sent
```

## Plan — files to change

- `src/overdue.ts` — decide which invoices are overdue.
- `src/reminder-mailer.ts` — send the reminder email once per overdue invoice.
- `tests/overdue.test.ts` — cover all three criteria and the scenario.
