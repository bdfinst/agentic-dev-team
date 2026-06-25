# Change 3: final curve

Add a `curve` keyword argument to `final_grade(categories, curve=0)`. It is a
number of points added to the **final weighted percentage**.

The curve is applied **after** all categories have been weighted and summed, but
**before** the percentage is rounded and the letter is looked up. Because it is
added before the letter lookup, the curve can push a grade across a letter
boundary.

Details:

- After adding the curve, **cap the final percentage at 100** (a curve can never
  produce more than 100).
- Then round-half-up and look up the letter exactly as before.
- `curve` defaults to `0` (no change, unchanged behavior).

The order is now: **per-category average → × weight → sum → + curve → cap at 100
→ round-half-up → letter lookup**.

### Worked examples

- `final_grade([{"name": "a", "weight": 0.5, "scores": [70]},
  {"name": "b", "weight": 0.5, "scores": [86]}], curve=5)` → `(83, "B")`
  (0.5×70 + 0.5×86 = 78, + `5` curve → `83`; without the curve it would be a `"C"`)
- `final_grade([{"name": "a", "weight": 1.0, "scores": [88]}], curve=2)` → `(90, "A")`
  (88 + `2` = `90`; the curve crosses the A boundary — the letter must be looked
  up after the curve, not before)
- `final_grade([{"name": "a", "weight": 1.0, "scores": [98]}], curve=5)` → `(100, "A")`
  (98 + `5` = `103`, capped at `100`)
- `final_grade([{"name": "a", "weight": 1.0, "scores": [75]}], curve=0)` → `(75, "C")`
  (unchanged)
