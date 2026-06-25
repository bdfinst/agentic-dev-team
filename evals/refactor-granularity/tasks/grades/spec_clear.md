# Spec: weighted gradebook calculator

Implement `final_grade(categories)` in `grades.py`. It returns a tuple
`(percent, letter)` where `percent` is an **integer** and `letter` is a
single-character **string**. Every rule below is fixed — there are no decisions
left to your judgment.

## Input shape

`categories` is a list of dicts. Each dict has exactly these keys:

| key | type | meaning |
|---|---|---|
| `"name"` | str | label for the category (e.g. `"homework"`) |
| `"weight"` | float | fraction of the final grade this category is worth |
| `"scores"` | list of numbers | the raw scores in that category |

## Category average

A category's average is the **arithmetic mean of its scores** (sum of the scores
divided by how many there are).

## Weighted percentage

Each category contributes `weight × category_average` to a running total. The
final weighted percentage is the **sum of those contributions** across all
categories.

The `weight` values **must sum to exactly `1.0`**. If they do not, raise
`ValueError`.

## Rounding and letter grade

Round the weighted percentage to the nearest whole number using
**round-half-up** (a fraction of exactly 0.5 rounds up), then look up the letter
from the rounded integer:

| rounded percent | letter |
|---|---|
| 90 and above | `"A"` |
| 80 up to 89 | `"B"` |
| 70 up to 79 | `"C"` |
| 60 up to 69 | `"D"` |
| below 60 | `"F"` |

Boundaries belong to the **higher** band: exactly `90` is `"A"`, exactly `80` is
`"B"`. The rounding happens **before** the letter lookup — a weighted percentage
of `89.5` rounds to `90` and is therefore an `"A"`.

## Error cases

- A category whose `"scores"` list is **empty** must raise `ValueError`.
- A score **below 0 or above 100** must raise `ValueError`.
- `weight` values that do **not** sum to `1.0` must raise `ValueError`.

## Order and rounding

The computation runs strictly in this order: **category average → multiply by
weight → sum the contributions → round-half-up → look up the letter**.
Intermediate values are not rounded.

### Worked examples

- `final_grade([{"name": "hw", "weight": 0.4, "scores": [80]},
  {"name": "ex", "weight": 0.6, "scores": [90]}])` → `(86, "B")`
  (0.4 × 80 + 0.6 × 90 = 32 + 54 = 86)
- `final_grade([{"name": "a", "weight": 0.5, "scores": [82]},
  {"name": "b", "weight": 0.5, "scores": [83]}])` → `(83, "B")`
  (0.5 × 82 + 0.5 × 83 = 82.5 → round-half-up → 83)
- `final_grade([{"name": "a", "weight": 1.0, "scores": [90]}])` → `(90, "A")`
  (boundary belongs to the higher band)
- `final_grade([{"name": "a", "weight": 1.0, "scores": [40]}])` → `(40, "F")`
