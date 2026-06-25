# Change 1: daily fare cap

Add a function `day_total(rides, daily_cap_cents=1000)` to `fare.py`.

`rides` is a list of dicts; each dict holds keyword arguments for `fare()` (e.g.
`{"distance_km": 7, "passenger": "child"}`). Compute each ride's fare with the
existing rules, summing them in order, but **never let the running total exceed
`daily_cap_cents`**. The ride that would cross the cap is charged only the
remaining amount up to the cap; rides after the cap is reached cost 0.

Return the total cents for the day.

### Worked examples

- `day_total([{"distance_km": 3}, {"distance_km": 7}])` → 550
- `day_total([{"distance_km": 7}] * 3)` → 1000 (350 + 350 + 300-clipped)
- `day_total([{"distance_km": 12}] * 5)` → 1000 (500 + 500, rest free)
- `day_total([{"distance_km": 7}, {"distance_km": 7}], daily_cap_cents=400)` → 400
