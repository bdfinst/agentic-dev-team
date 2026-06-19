# Spec — String Calculator `add`

Implement `add(numbers: str) -> int` in `string_calc.py`.

## Rules

1. An empty string returns `0`.
2. A single number returns its value.
3. Two or more numbers, comma-separated, return their sum.
4. Newlines (`\n`) are also valid delimiters, interchangeable with commas
   (e.g. `"1\n2,3"` returns `6`).

## Acceptance

`python3 test_string_calc.py` must exit `0` — every case in that file passes.
Do not modify the test file; implement only `string_calc.py`.
