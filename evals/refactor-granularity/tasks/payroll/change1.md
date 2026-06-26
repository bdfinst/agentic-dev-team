# Change 1: overtime gross

Add a function `gross_from_hours(hours, hourly_rate_cents)` to `payroll.py` that
computes gross pay in integer cents from hours worked.

Hours up to and including **40** are paid at the regular rate. Hours **beyond
40** are overtime, paid at **1.5×** the hourly rate:

```
gross = min(hours, 40) × hourly_rate_cents
      + max(hours − 40, 0) × hourly_rate_cents × 1.5
```

Round the gross to the nearest cent with round-half-up. The result feeds
straight into `net_pay()` as its `gross_cents` argument — overtime is part of
gross, so it is taxed normally. Negative `hours` or negative
`hourly_rate_cents` must raise `ValueError`.

### Worked examples

- `gross_from_hours(40, 2500)` → 100000 (no overtime)
- `gross_from_hours(45, 2500)` → 118750 (100000 + 5 × 2500 × 1.5 = 100000 + 18750)
- `gross_from_hours(50, 2000)` → 110000 (80000 + 10 × 2000 × 1.5 = 80000 + 30000)
- `net_pay(gross_from_hours(45, 2500))` → 105000 (gross 118750, tax 10000 + 20% × 18750 = 13750)
