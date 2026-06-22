# Feature: mini-spreadsheet (`sheet` package)

A tiny in-memory spreadsheet. Implement across two source modules plus the
public re-export in `sheet/__init__.py`:

- `sheet/parse.py` — tokenizes and parses formula expressions.
- `sheet/core.py` — holds the `Sheet` class, evaluation, range expansion,
  and cycle detection.

The public surface, importable directly from `sheet`, is exactly:
`Sheet`, `CycleError`, `parse`, `tokenize`.

## Cell addresses

A cell address is column letters (`A`–`Z`, then `AA`, `AB`, …, base-26
bijective) followed by a 1-based row number. Examples: `"A1"`, `"B2"`, `"Z9"`,
`"AA1"`. Addresses are case-sensitive uppercase in tests.

## Cell contents

A cell holds either:

- a **literal number** (`int` or `float`), or
- a **formula string** that starts with `"="` (e.g. `"=A1+B2"`).

`Sheet.set_cell(addr, value)` stores the value. `Sheet.get_raw(addr)` returns
exactly what was stored (the original number or the original formula string,
including the leading `"="`). For a cell that was never set, `get_raw` returns
`None`.

`Sheet.get_value(addr)` returns the evaluated value as a **`float`**:

- A literal number returns its value as a float.
- An **empty** (never-set) cell evaluates to `0.0`.
- A formula is evaluated by parsing it and resolving references recursively.

`Sheet()` takes no constructor arguments.

## Formula language

The formula body is the text after the leading `"="`. It supports:

- numeric literals (integers and decimals, e.g. `3`, `2.5`),
- cell references (e.g. `A1`),
- binary operators `+`, `-`, `*`, `/` with standard precedence
  (`*` and `/` bind tighter than `+` and `-`), left-associative,
- parentheses for grouping,
- the functions `SUM(range)` and `AVG(range)` (see below).

`tokenize(body)` returns a list of tokens for the formula body (text after
`"="`). `parse(body)` returns an AST that `core` evaluation consumes. Their
exact token/AST shapes are an implementation detail and are NOT asserted
directly; tests exercise them only through `Sheet.get_value`. Both are exported
so the evaluator and tests can reach them, but you choose their internal form.

A reference to an empty cell inside an arithmetic expression contributes `0.0`.

## Ranges and functions

A range is written `START:END` where both ends are addresses, e.g. `A1:A3` or
`A1:B2`. The range is the **inclusive rectangular block** of cells between the
two corners (min/max of columns and rows are taken, so `B2:A1` equals
`A1:B2`). Range cells are ordered row-major (row 1 left-to-right, then row 2,
…) when iterated, though order does not affect `SUM`/`AVG` results.

- `SUM(range)` — the sum of `get_value` over every cell in the range.
- `AVG(range)` — the arithmetic mean of `get_value` over every cell in the
  range (sum divided by the count of cells in the rectangle, including empty
  cells which count as `0.0`).

Ranges appear only as the sole argument of `SUM`/`AVG`; they are not valid in
plain arithmetic.

## Cycle detection

If evaluating a cell requires (transitively) the value of that same cell, the
evaluation must raise `CycleError` (defined in `core`, exported from `sheet`).
Example: `A1 = "=B1"`, `B1 = "=A1"` → `get_value("A1")` raises `CycleError`.
A cell referencing itself directly (`A1 = "=A1"`) also raises `CycleError`.

## Division by zero

A formula that divides by zero raises `ZeroDivisionError` with a clear
message when evaluated. This includes dividing by an empty cell (value `0.0`).

## Acceptance scenarios

1. **Literal value.** `set_cell("A1", 5)` → `get_value("A1") == 5.0`;
   `get_raw("A1") == 5`.
2. **Empty cell is 0.** A never-set cell `Z9` → `get_value("Z9") == 0.0` and
   `get_raw("Z9") is None`.
3. **Simple arithmetic formula.** `A1=2`, `B2=3`, `C1="=A1+B2"` →
   `get_value("C1") == 5.0`.
4. **Precedence and parentheses.** `A1=2`, `B1=3`, `C1=4`;
   `"=A1+B1*C1"` → `14.0`; `"=(A1+B1)*C1"` → `20.0`.
5. **Chained references.** `A1="=B1"`, `B1="=C1"`, `C1=7` →
   `get_value("A1") == 7.0`.
6. **SUM over a range.** `A1=1`, `A2=2`, `A3=3`, `S="=SUM(A1:A3)"` →
   `get_value("S") == 6.0` (here `S` is any unused address, e.g. `B1`).
7. **AVG over a rectangle.** `A1=1`, `A2=3`, `B1=5`, `B2=7`,
   `"=AVG(A1:B2)"` → `4.0` (sum 16 over 4 cells). With one cell empty, the
   empty cell counts as `0.0` in both sum and count.
8. **Cycle detection.** `A1="=B1"`, `B1="=A1"` → `get_value("A1")` raises
   `CycleError`. Also `A1="=A1"` raises `CycleError`.
9. **Division by zero.** `A1="=1/0"` raises `ZeroDivisionError`; dividing by
   an empty cell (`A1="=5/B9"` with `B9` empty) also raises
   `ZeroDivisionError`.

All numeric results from `get_value` are floats. Formula evaluation must be
deterministic.
