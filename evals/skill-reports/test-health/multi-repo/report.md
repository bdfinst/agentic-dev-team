# Test Health

## Test Health: orders, billing (2026-11-19)

### Quadrant coverage

Quadrant 2 and 3 coverage is thin in billing.

### System-level test design (via system-test-design)

Source: `.dev-team-reports/system-test-design-orders.md`.

- Minimum E2E set: Place an order and see it billed; Cancel an order. Both guard the orders and billing handoff.
- Overlap findings: 2 `coverage-backed`, 1 `static-judgment`. Trim the component tests named in the source report.

Existing E2E classifications stay in the source report.

### Improvement plan (ordered)

1. Pin the orders to billing boundary with a contract test.
