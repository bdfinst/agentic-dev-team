# Change 2: per-category discount caps

Line items may now carry an optional `"category"` string. Two categories have a
**cap on the total discount** (bulk discount plus order coupon, in cents) that
any single line in that category may receive:

| category | discount cap (cents) |
|---|---|
| `"electronics"` | 2000 |
| `"apparel"` | 500 |

For a line in a capped category, compute its bulk discount and coupon discount as
in Change 1, then **clamp the line's combined discount to the cap** before
subtracting it from that line's gross. A line whose category is not in the table
(including a line with no `"category"` key) is uncapped.

The cap is **per line**, measured against that line's own gross — not against the
order total. After clamping, the line's net joins the discounted subtotal and the
order is taxed at 8% as before.

### Worked examples

- `checkout([{"price_cents": 1000, "qty": 30, "category": "electronics"}])` → 30240
  (gross 30000, bulk 3000 → clamped to 2000, net 28000, × 1.08)
- `checkout([{"price_cents": 300, "qty": 20, "category": "apparel"}])` → 5940
  (gross 6000, bulk 600 → clamped to 500, net 5500, × 1.08)
- `checkout([{"price_cents": 300, "qty": 20, "category": "apparel"}], coupon_pct=50)` → 5940
  (bulk 600 + coupon 2700 = 3300 → clamped to 500, net 5500, × 1.08)
- `checkout([{"price_cents": 500, "qty": 10, "category": "electronics"}])` → 4860
  (gross 5000, bulk 500 < cap 2000 → unclamped, net 4500, × 1.08)
