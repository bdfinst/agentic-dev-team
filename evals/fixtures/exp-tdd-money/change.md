# Change: add split
Add `split(cents, n)` to `money.py`: divide `cents` into `n` integer parts that
sum exactly to `cents`, distributing any remainder one cent at a time to the
earliest parts (so split(100,3) == [34,33,33]). parse/format must not change.
