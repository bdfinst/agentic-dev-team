# Change 2: Category-Scoped Discounts (TRAP CHANGE)

Add a `category` parameter to `Discount`:

```python
Discount(discount_type, value, priority=0, group=None, min_qty=1, category=None)
```

**Semantics:** A discount with a `category` string (e.g. `"Electronics"`) applies
**only to the subtotal of items whose `category` field matches** that string. The
discount amount computed on the category subtotal is then subtracted from the
running cart total.

- A discount with `category=None` (the default) applies to the full running total,
  as before.
- Category matching is case-sensitive and exact.
- Items without a `"category"` key do not match any category discount.
- All other rules (priority, groups, floor, rounding, `min_qty`) are unchanged.

**Design impact:** implementations that apply discounts directly to the running
cart total (rather than passing item context to each discount) will need to
restructure: a category-scoped discount must receive the list of items to compute
its own savings, rather than receiving the aggregate total.

**Examples:**
- Cart: `[{"price": 100, "category": "Electronics"}, {"price": 50, "category": "Books"}]`
- Discount: `Discount("percent", 20, category="Electronics")` → saves 20% of $100 = $20
  → cart total becomes $130.00 (not $120 — Books subtotal is unaffected)
- Discount: `Discount("fixed", 10, category="Books")` → saves $10 from Books subtotal
  → cart total becomes $140.00 (not $130 — Electronics subtotal is unaffected)
- Two category discounts (Electronics 20%, Books 10%) + one global 5% fixed:
  → category discounts applied first (on their subtotals), then global fixed on running total
