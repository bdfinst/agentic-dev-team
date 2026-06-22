# Change: add top_n

Add `top_n(text, n)` to `tally.py`, reusing `word_count`.

- Returns a list of `(word, count)` tuples for the `n` highest-count words.
- Sort by count descending, then word ascending for ties.
- `top_n("", 3)` returns `[]`.
- Existing `word_count` behavior must not change.
