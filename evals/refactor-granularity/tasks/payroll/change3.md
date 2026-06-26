# Change 3: married filing status

Allow `filing_status="married"` in `net_pay()`, with its own progressive
brackets. The `"single"` brackets are unchanged. The `"married"` brackets are
wider:

| taxable income (cents) | single rate | married rate |
|---|---|---|
| 0 up to and including 100000 | 10% | 10% |
| above 100000 up to and including 200000 | 20% | 10% |
| above 200000 up to and including 300000 | 20% | 20% |
| above 300000 up to and including 500000 | 30% | 20% |
| above 500000 | 30% | 30% |

So for `"married"`: the first 200000 cents are taxed at 10%, the next 300000
cents (up to 500000) at 20%, and everything beyond 500000 at 30%. The brackets
apply to the **same taxable income** the pre-tax retirement deduction produced;
the post-tax garnishment from Change 2 still applies last and unchanged.

`filing_status` defaults to `"single"`. Any status other than `"single"` or
`"married"` must raise `ValueError`.

### Worked examples

- `net_pay(200000, "married")` → 180000 (taxable 200000 all at 10% = 20000)
- `net_pay(400000, "married")` → 340000 (10% × 200000 + 20% × 200000 = 60000)
- `net_pay(400000, "single")` → 320000 (unchanged: tax 80000)
- `net_pay(600000, "married")` → 490000 (20000 + 60000 + 30% × 100000 = 110000)
