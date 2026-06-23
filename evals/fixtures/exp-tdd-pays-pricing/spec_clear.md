# Pricing Engine — Full Specification

Build a `PricingEngine` class in `pricing.py` that applies a configurable,
priority-ordered stack of discounts to a shopping cart.

## Public API

```python
from pricing import PricingEngine, Discount

engine = PricingEngine()
engine.add_discount(discount)
total: float = engine.calculate(items)
```

### Items
`items` is a list of dicts, each with:
- `price` (float): unit price ≥ 0
- `qty` (int, optional, default 1): quantity ≥ 1
- `category` (str, optional): product category label (e.g. `"Electronics"`)

### Discount constructor
```python
Discount(discount_type, value, priority=0, group=None)
```
- `discount_type`: `"percent"` or `"fixed"`
- `value`: non-negative float
- `priority` (int, default 0): discounts with higher `priority` are applied before
  lower-priority ones; ties broken by insertion order (first-added applies first)
- `group` (str or None, default None): discounts sharing a `group` string are
  **mutually exclusive** — within a group only the discount with the highest
  `priority` applies; ties broken by insertion order (first inserted wins).
  Standalone discounts (`group=None`) always apply.

## Module shape
Single file: `pricing.py` at the repo root. Export both `PricingEngine` and `Discount`.

## Computation rules (apply in this order)

1. Compute the cart subtotal: `sum(item["price"] * item.get("qty", 1) for item in items)`
2. **Group resolution:** for each unique `group` value, select only the discount with
   the highest `priority`; tie goes to the one inserted first.
3. **Application order:** collect the group winners plus all standalone discounts;
   sort descending by `priority`, ties by insertion order.
4. Apply each selected discount to the running total in that order:
   - `"percent"`: `total *= (1 - value / 100)`
   - `"fixed"`: `total -= value`
5. Floor at 0.0, then round to 2 decimal places and return.

## Edge-case decisions

- `calculate([])` → `0.0`
- Item without `"qty"` key → quantity defaults to 1
- Discount with `value=0` → no-op (does not raise)
- Discount that would make total negative → total is clamped to 0.0
- `"percent"` discount with `value=100` → total becomes 0.0 after clamp

## Acceptance scenarios (≥ 8)

1. Empty cart → 0.0
2. No discounts, multi-item cart → sum of price×qty (e.g. 3×$25 = $75.00)
3. Single 10% discount on $100 cart → 90.0
4. Single $15 fixed discount on $100 cart → 85.0
5. Two standalone discounts stack: 10% + $5 fixed on $100 → 85.0
   (after 10%: $90; after $5: $85.00)
6. Exclusive group: 20% (priority 2) and 10% (priority 1) both in `group="promo"` on $100
   → only the higher-priority 20% discount applies → 80.0
7. Group winner + standalone: 20% (group="promo") + $5 standalone on $100 → 75.0
8. Priority ordering: fixed $10 (priority 1, inserted first) and 50% (priority 10,
   inserted second) on $100 → 50% applies first: 50.0 – 10 = 40.0
9. Negative floor: $10 cart with $20 fixed discount → 0.0
10. Rounding: 33% off $10.00 → 6.70
