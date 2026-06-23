# Change 1: Minimum Quantity Threshold

Add a `min_qty` parameter to `Discount`:

```python
Discount(discount_type, value, priority=0, group=None, min_qty=1)
```

**Semantics:** A discount with `min_qty=N` only applies when the **total number of
items** in the cart (summing all `qty` values, defaulting to 1 per item) is at
least `N`. Discounts with `min_qty=1` (the default) always apply as before.

**Rules:**
- A discount whose `min_qty` is not met is simply skipped — it does not participate
  in group resolution either (as if it were never registered for this calculation).
- All existing behaviour (priority, groups, floor, rounding) is unchanged.
- Existing code that does not pass `min_qty` must continue to work unchanged.

**Examples:**
- Cart has 2 items (qty 1 each). Discount with `min_qty=3` → not applied.
- Cart has 3 items (qty 1 each). Discount with `min_qty=3` → applied.
- Cart has 1 item with `qty=5`. Total qty = 5 ≥ 3 → discount applied.
