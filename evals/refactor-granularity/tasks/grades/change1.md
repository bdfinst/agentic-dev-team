# Change 1: drop each category's lowest score

Before averaging a category, **drop its single lowest score** — but only when the
category has **more than one** score. A category with exactly one score keeps it.

So a category's average is now the mean of its scores **after** the lowest one is
removed. If several scores tie for lowest, drop exactly one of them.

Everything else (weighting, the `1.0` weight-sum rule, round-half-up, the letter
scale) is unchanged. The 0..100 range check and the empty-`scores` `ValueError`
still apply to the original list, before anything is dropped.

### Worked examples

- `final_grade([{"name": "a", "weight": 1.0, "scores": [60, 90, 90]}])` → `(90, "A")`
  (drop the `60`, mean of `[90, 90]` is `90`)
- `final_grade([{"name": "a", "weight": 1.0, "scores": [70, 90]}])` → `(90, "A")`
  (drop the `70`, only `90` remains)
- `final_grade([{"name": "a", "weight": 1.0, "scores": [60]}])` → `(60, "D")`
  (single score is never dropped)
- `final_grade([{"name": "hw", "weight": 0.5, "scores": [50, 100, 90]},
  {"name": "ex", "weight": 0.5, "scores": [80, 80]}])` → `(88, "B")`
  (hw: drop `50` → mean `95`; ex: drop one `80` → `80`; 0.5×95 + 0.5×80 = 87.5 → 88)
