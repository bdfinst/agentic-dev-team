# Change 1: order-level coupon

Add a `coupon_pct` keyword argument to `checkout(items, coupon_pct=0)`. It is a
whole-order percentage discount applied **after** the per-line bulk discount and
**before** sales tax.

For each line, after its bulk discount, take `coupon_pct` percent off whatever
remains of that line, then sum the lines into the discounted subtotal and tax it
at 8% as before. `coupon_pct` defaults to 0 (no coupon, unchanged behavior). A
`coupon_pct` below 0 or above 100 must raise `ValueError`.

The order is now: **line gross → bulk discount → order coupon → discounted
subtotal → 8% tax**.

### Worked examples

- `checkout([{"price_cents": 1000, "qty": 1}], coupon_pct=10)` → 972 (900 × 1.08)
- `checkout([{"price_cents": 100, "qty": 10}], coupon_pct=10)` → 875 (bulk 900, −10% = 810, × 1.08 = 874.8 → 875)
- `checkout([{"price_cents": 1000, "qty": 1}, {"price_cents": 500, "qty": 2}], coupon_pct=25)` → 1620 (2000 × 0.75 = 1500, × 1.08)
- `checkout([{"price_cents": 1000, "qty": 1}], coupon_pct=0)` → 1080 (unchanged)
