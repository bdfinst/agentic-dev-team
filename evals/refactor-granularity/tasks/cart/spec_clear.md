# Spec: shopping cart checkout calculator

Implement `checkout(items)` in `cart.py`. It returns the order total as an
**integer number of cents**. Every rule below is fixed — there are no decisions
left to your judgment.

## Input

`items` is a list of line-item dicts. Each dict has:

| key | meaning |
|---|---|
| `"price_cents"` | unit price in integer cents |
| `"qty"` | quantity of that line |

A dict may carry other keys; ignore any key that is not listed above. An empty
`items` list is valid and totals `0`.

## Line gross

Each line's **gross** is `price_cents × qty`. A **negative** `price_cents` must
raise `ValueError`; a **negative** `qty` must raise `ValueError`. A `qty` of `0`
is valid (that line's gross is `0`).

## Bulk discount

A line whose `qty` is **10 or more** receives a **10% bulk discount** off that
line's gross. Lines with `qty` below 10 get no discount. The discount is
computed **per line**, not on the order total.

## Sales tax

After the bulk discount, the **discounted subtotal** (the sum of every line's
gross minus its bulk discount) is taxed at **8%**.

## Order and rounding

The total is computed strictly in this order: **sum line gross → apply the
per-line bulk discount → sum to the discounted subtotal → apply 8% sales tax**.
Discount before tax. The final amount is rounded to the nearest whole cent using
**round-half-up** (a fraction of exactly 0.5 rounds up). Use `Decimal`
arithmetic; intermediate values are not rounded.

### Worked examples

- `checkout([{"price_cents": 1000, "qty": 1}])` → 1080 (1000 × 1.08)
- `checkout([{"price_cents": 1000, "qty": 2}, {"price_cents": 500, "qty": 3}])` → 3780 (3500 × 1.08)
- `checkout([{"price_cents": 100, "qty": 10}])` → 972 (qty ≥ 10: 1000 − 10% = 900, × 1.08)
- `checkout([{"price_cents": 100, "qty": 9}])` → 972 (no bulk discount: 900 × 1.08)
- `checkout([{"price_cents": 333, "qty": 3}])` → 1079 (999 × 1.08 = 1078.92 → 1079)
- `checkout([])` → 0
