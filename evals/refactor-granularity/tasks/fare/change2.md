# Change 2: transfer discount

Extend `day_total` so that rides can carry an optional `"start_min"` key (minutes
since midnight). A ride whose `start_min` is **within 90 minutes after the
previous ride's `start_min`** is a transfer and is charged at **half** its normal
fare (round-half-up to the nearest cent).

Details:

- The 90-minute window is measured from the **previous ride's start**, and the
  boundary is inclusive: exactly 90 minutes later still counts as a transfer.
- The half-price is computed **before** the daily cap from Change 1 is applied.
- Rides without `start_min` never qualify as a transfer and do not start a
  transfer window; the "previous start" carries over from the last ride that had
  one.

### Worked examples

- `day_total([{"distance_km": 7, "start_min": 0}, {"distance_km": 7, "start_min": 60}])` → 525 (350 + 175)
- `day_total([{"distance_km": 7, "start_min": 0}, {"distance_km": 7, "start_min": 90}])` → 525 (boundary)
- `day_total([{"distance_km": 7, "start_min": 0}, {"distance_km": 7, "start_min": 91}])` → 700 (full)
- `day_total([{"distance_km": 3, "start_min": m} for m in (0, 80, 160)])` → 400 (200 + 100 + 100)
