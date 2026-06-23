# Pricing Engine

Build a `PricingEngine` class in `pricing.py` that calculates the total cost of
a shopping cart after applying one or more discounts.

## Public API

```python
from pricing import PricingEngine, Discount

engine = PricingEngine()
engine.add_discount(discount)
total = engine.calculate(items)
```

### Items
`items` is a list of dicts. Each dict has:
- `price` (float): unit price
- `qty` (int, optional, default 1): quantity
- `category` (str, optional): product category label

### Discount
A `Discount` is created as:
```python
Discount(discount_type, value)
```
- `discount_type`: `"percent"` (reduce by a percentage) or `"fixed"` (reduce by a fixed amount)
- `value`: the discount amount (a non-negative number)

## Behavior
- `calculate(items)` returns the total price as a float after all discounts are applied
- Multiple discounts are all applied to the cart
- The total cannot go below zero
- The return value is rounded to 2 decimal places
