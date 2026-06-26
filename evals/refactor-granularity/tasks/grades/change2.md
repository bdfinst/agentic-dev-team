# Change 2: per-category extra credit

A category dict may now carry an optional `"extra_credit"` key — a number of
points added to that category's average. When the key is absent, treat it as `0`
(unchanged behavior).

Details:

- The extra-credit points are added to the category average **after** the
  lowest score has been dropped (Change 1) and the mean computed — not to the
  raw scores.
- A category average can never exceed `100`: after adding extra credit, **cap
  the category average at 100**.
- The cap applies to the category average only. Weighting, the final round, and
  the letter lookup are unchanged.

### Worked examples

- `final_grade([{"name": "a", "weight": 1.0, "scores": [80, 90], "extra_credit": 5}])` → `(95, "A")`
  (drop `80` → mean `90`, + `5` extra → `95`)
- `final_grade([{"name": "a", "weight": 1.0, "scores": [95, 99], "extra_credit": 10}])` → `(100, "A")`
  (drop `95` → mean `99`, + `10` → `109`, capped at `100`)
- `final_grade([{"name": "a", "weight": 1.0, "scores": [40, 80], "extra_credit": 10}])` → `(90, "A")`
  (extra credit is added after the drop: drop `40` → mean `80`, + `10` → `90`)
- `final_grade([{"name": "hw", "weight": 0.4, "scores": [70, 90]},
  {"name": "ex", "weight": 0.6, "scores": [60, 60], "extra_credit": 20}])` → `(84, "B")`
  (hw: drop `70` → `90`; ex: drop one `60` → `60`, + `20` → `80`; 0.4×90 + 0.6×80 = 84)
