# Spec: payroll net-pay calculator

Implement `net_pay(gross_cents, filing_status="single", retirement_pct=0)` in
`payroll.py`. It returns the net pay as an **integer number of cents**. Every
rule below is fixed — there are no decisions left to your judgment.

## Pre-tax retirement deduction

A `retirement_pct` percentage of **gross** is set aside before any tax is
computed. The retirement deduction is `gross_cents × retirement_pct / 100`. The
amount remaining after this deduction is the **taxable income**:

```
taxable = gross_cents − (gross_cents × retirement_pct / 100)
```

`retirement_pct` defaults to `0` (no deduction). A `retirement_pct` below `0` or
above `100` must raise `ValueError`.

## Progressive tax brackets

Tax is computed on the **taxable income** (not on gross) using progressive
brackets for filing status `"single"`. Each bracket's rate applies only to the
portion of taxable income that falls within that bracket:

| taxable income (cents) | marginal rate |
|---|---|
| 0 up to and including 100000 | 10% |
| above 100000 up to and including 300000 | 20% |
| above 300000 | 30% |

So the first 100000 cents are always taxed at 10%, the next 200000 cents at 20%,
and everything beyond 300000 cents at 30%. Any `filing_status` other than
`"single"` must raise `ValueError`.

## Net pay

Net pay is gross minus the pre-tax retirement deduction minus the tax:

```
net = gross_cents − retirement_deduction − tax
```

A **negative** `gross_cents` must raise `ValueError`. A gross of `0` is valid
(net 0).

## Order and rounding

The net pay is computed strictly in this order: **retirement deduction →
taxable income → progressive tax → subtract from gross**. The retirement
deduction reduces taxable income **before** the brackets apply. The final amount
is rounded to the nearest whole cent using **round-half-up** (a fraction of
exactly 0.5 rounds up). Intermediate values are not rounded.

### Worked examples

- `net_pay(50000)` → 45000 (tax 10% of 50000 = 5000)
- `net_pay(200000)` → 170000 (tax = 10000 + 20% × 100000 = 30000)
- `net_pay(400000)` → 320000 (tax = 10000 + 40000 + 30% × 100000 = 80000)
- `net_pay(200000, retirement_pct=10)` → 154000 (pre-tax 20000, taxable 180000,
  tax 10000 + 20% × 80000 = 26000, net = 200000 − 20000 − 26000)
- `net_pay(300, retirement_pct=5)` → 257 (pre-tax 15, taxable 285, tax 28.5,
  net = 300 − 15 − 28.5 = 256.5 → 257)
- `net_pay(0)` → 0
