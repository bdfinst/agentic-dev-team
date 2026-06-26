# Change 3: tax-exempt categories

Two categories are **exempt from sales tax**:

| category | taxed? |
|---|---|
| `"groceries"` | no |
| `"books"` | no |
| everything else | yes (8%) |

The 8% sales tax no longer applies to the whole order. Instead, after each line's
gross, bulk discount, order coupon, and category cap are resolved (Changes 1–2),
the line's **net** joins one of two subtotals by its category: a **taxed**
subtotal or a **tax-exempt** subtotal. Only the taxed subtotal is multiplied by
1.08; the exempt subtotal is added in untouched. The final total is rounded
round-half-up to whole cents as before.

`"groceries"` and `"books"` are not in the discount-cap table from Change 2, so
they remain uncapped — they are only affected by the tax exemption.

The order is now: **per line → gross → bulk discount → order coupon → category cap
→ route net to the taxed or tax-exempt subtotal**, then **8% tax on the taxed
subtotal only → sum → round**.

### Worked examples

- `checkout([{"price_cents": 1000, "qty": 1, "category": "groceries"}])` → 1000 (exempt, no tax)
- `checkout([{"price_cents": 1000, "qty": 1, "category": "books"}])` → 1000 (exempt, no tax)
- `checkout([{"price_cents": 1000, "qty": 1, "category": "groceries"}, {"price_cents": 1000, "qty": 1}])` → 2080
  (1000 exempt + 1000 × 1.08)
- `checkout([{"price_cents": 100, "qty": 10, "category": "groceries"}], coupon_pct=10)` → 810
  (bulk 900, coupon −10% = 810, exempt → no tax)
