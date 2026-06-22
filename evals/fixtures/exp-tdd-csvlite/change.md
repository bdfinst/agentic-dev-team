# Change: add to_csv
Add `to_csv(rows)` to `csvlite.py`, the inverse of `parse`: render rows back to a
CSV string, quoting any field that contains a comma, quote, or newline and
doubling internal quotes. `parse` must not change.
