# Change: add from_roman

Add `from_roman(s)` to `roman.py`.

- Parses a valid Roman numeral string back to its integer value.
- Must round-trip: `from_roman(to_roman(n)) == n` for all `1..3999`.
- Existing `to_roman` behavior must not change.
