# Change 2: post-tax garnishment

Add a `garnishment_cents` keyword argument to
`net_pay(gross_cents, filing_status="single", retirement_pct=0, garnishment_cents=0)`.

A garnishment is a fixed amount withheld **after** tax. Unlike the pre-tax
retirement deduction, the garnishment does **not** reduce taxable income — tax
is still computed on the same taxable income as before, and the garnishment is
subtracted from the result:

```
net = gross_cents − retirement_deduction − tax − garnishment_cents
```

The garnishment is a flat number of cents, not a percentage. It defaults to `0`
(unchanged behavior). A negative `garnishment_cents` must raise `ValueError`.

The order is now: **retirement deduction → taxable income → tax → garnishment**.
The garnishment is applied last and only after tax has been computed on the
pre-tax-reduced taxable income.

### Worked examples

- `net_pay(200000, garnishment_cents=5000)` → 165000 (tax 30000, then − 5000)
- `net_pay(200000, retirement_pct=10, garnishment_cents=5000)` → 149000
  (pre-tax 20000, taxable 180000, tax 26000, net 154000, then − 5000)
- `net_pay(200000, garnishment_cents=0)` → 170000 (unchanged)
