# Spec: transit fare calculator

Implement `fare(distance_km, passenger="adult", peak=False)` in `fare.py`. It
returns the fare as an **integer number of cents**. Every rule below is fixed —
there are no decisions left to your judgment.

## Base fare by distance band

The base fare depends on the trip distance in kilometers:

| distance (km) | base fare (cents) |
|---|---|
| 0 up to and including 5 | 200 |
| above 5 up to and including 10 | 350 |
| above 10 | 500 |

Boundaries belong to the **lower** band: exactly `5.0` km is 200 cents, exactly
`10.0` km is 350 cents. A distance of `0` is valid (200 cents). A **negative**
distance must raise `ValueError`.

## Peak multiplier

If `peak` is true, multiply the base fare by **1.5**. If false, no change.

## Passenger discount

After the peak multiplier is applied, reduce the fare by the passenger's
discount percentage:

| passenger | discount |
|---|---|
| `"adult"` | 0% |
| `"child"` | 50% |
| `"senior"` | 30% |

Any other passenger value must raise `ValueError`.

## Order and rounding

The fare is computed strictly in this order: **base fare → apply peak multiplier
→ apply passenger discount**. The final amount is rounded to the nearest whole
cent using **round-half-up** (a fraction of exactly 0.5 rounds up). Intermediate
values are not rounded.

### Worked examples

- `fare(7)` → 350
- `fare(3, peak=True)` → 300 (200 × 1.5)
- `fare(7, "child")` → 175
- `fare(7, "senior", peak=True)` → 368 (350 × 1.5 = 525, × 0.70 = 367.5 → 368)
- `fare(5.0)` → 200 (boundary belongs to the lower band)
