# Change: add decode

Add `decode(s)` to `rle.py`, the inverse of `encode`, so
`decode(encode(s)) == s` for any string. Counts may be multi-digit.
`encode` behavior must not change.
