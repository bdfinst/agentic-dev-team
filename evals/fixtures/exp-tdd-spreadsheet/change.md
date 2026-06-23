# Change: aggregation functions, empty-string semantics, and clear_cell

This change modifies and extends behavior across `sheet/parse.py` and
`sheet/core.py`. The Stage-1 public surface still applies; this adds to it.

## 1. New range functions `MAX` and `MIN` (`parse.py` + `core.py`)

Add `MAX(range)` and `MIN(range)`:

- `MAX(range)` — the largest `get_value` over the cells in the range.
- `MIN(range)` — the smallest `get_value` over the cells in the range.

Like `SUM`/`AVG`, the argument is a single inclusive rectangular range.
`parse.py` must recognize the new function names; `core.py` computes the
aggregation. Empty cells participate as `0.0` for `MAX`/`MIN` (consistent with
arithmetic), EXCEPT where rule 2 below removes them.

## 2. `SUM` ignores empty-string cells but counts explicit `0` (`core.py`)

Change `SUM` so that a cell whose **raw value is the empty string `""`** is
skipped (contributes nothing and is not counted), while a cell holding an
explicit literal `0` (the number) is still summed as `0.0`. A never-set cell
continues to contribute `0.0` to `SUM` as before (it is not an `""` cell).

This means `set_cell(addr, "")` now stores an empty-string raw value, and that
cell is treated as "blank" by `SUM`. `get_value` on an `""` cell still returns
`0.0`. `AVG`, `MAX`, `MIN`, and plain arithmetic are unchanged by this rule:
they continue to treat `""` cells and never-set cells as `0.0`.

Example: `A1=10`, `A2=""`, `A3=0` → `SUM(A1:A3) == 10.0` (A2 skipped, A3
counts as 0). Previously (Stage 1) an `""` cell was not a defined input; now it
is explicitly blank for `SUM`.

## 3. `Sheet.clear_cell(addr)` (`core.py`)

Add `Sheet.clear_cell(addr)`: removes any stored value so the cell reverts to
never-set. After `clear_cell`, `get_raw(addr) is None` and
`get_value(addr) == 0.0`. Clearing a cell that was never set is a no-op.

## Preserved Stage-1 behavior

All Stage-1 scenarios still hold: literals, empty cells = 0.0, arithmetic with
precedence/parentheses, chained references, `SUM`/`AVG` over ranges of plain
numbers, cycle detection raising `CycleError`, and division by zero raising
`ZeroDivisionError`.
