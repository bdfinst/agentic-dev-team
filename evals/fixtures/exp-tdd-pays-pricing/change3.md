# Change 3: Global Discount Cap

Add a `max_discount_pct` parameter to `PricingEngine`:

```python
engine = PricingEngine(max_discount_pct=None)
```

**Semantics:** When `max_discount_pct` is a number between 0 and 100, the engine
ensures that the **total savings** (original subtotal minus final total) never
exceed `max_discount_pct` percent of the original subtotal. If the combined
discounts would exceed the cap, the final total is floored at
`subtotal * (1 - max_discount_pct / 100)` (then rounded to 2dp as normal).

- `max_discount_pct=None` (the default) means no cap — existing behaviour is
  unchanged.
- The cap is applied **after** all discounts have been computed (i.e. after group
  resolution, application order, floor-at-zero), not per-discount.
- The existing absolute floor at 0.0 still applies: the cap can never produce a
  negative total.
- Existing engines constructed without `max_discount_pct` must continue to work.

**Examples:**
- `max_discount_pct=50`, original $100 cart:
  - Combined discounts bring total to $30 → capped at $50.00
  - Combined discounts bring total to $60 → $60.00 (no cap triggered)
- `max_discount_pct=0`: no discount ever applies → total equals original subtotal.
- `max_discount_pct=100` + 150% effective discount → floored at $0.00 (cap = 100%
  discount, then absolute floor = 0.0).
