# Change 3: zone surcharge

Add a `zones` keyword argument to `fare(distance_km, passenger="adult",
peak=False, zones=1)`. Crossing multiple zones adds a surcharge of **100 cents
per zone beyond the first** — i.e. `(zones - 1) * 100` cents.

The surcharge is added to the **base fare before the peak multiplier**, so on a
peak ride the surcharge is multiplied by 1.5 as well. The passenger discount
still applies last. `zones` defaults to 1 (no surcharge, unchanged behavior). A
`zones` value below 1 must raise `ValueError`.

The order is now: **base fare → add zone surcharge → apply peak multiplier →
apply passenger discount**.

### Worked examples

- `fare(7, zones=2)` → 450 (350 + 100)
- `fare(7, peak=True, zones=2)` → 675 ((350 + 100) × 1.5)
- `fare(7, "child", peak=True, zones=2)` → 338 (675 × 0.5 = 337.5 → 338)
- `fare(7, zones=1)` → 350 (unchanged)
