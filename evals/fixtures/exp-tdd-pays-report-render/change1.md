# Change 1: Row Limit Option

Add a `row_limit` keyword option supported by the `render()` call:

```python
output = renderer.render(data, format_name, row_limit=None, **other_options)
```

**Semantics:** If `row_limit` is an integer N > 0, only the first N rows of `data`
are passed to the handler. If `len(data) <= N` or `row_limit=None` (the default),
all rows are passed.

**Rules:**
- `row_limit` is consumed by the renderer before the handler is called. The handler
  receives a (possibly truncated) list, not the original list.
- `row_limit=0` → handler receives an empty list.
- `row_limit` is NOT forwarded to the handler's `**options` — it is a renderer-level
  concern.
- All other options continue to be forwarded to the handler unchanged.
- Existing code that does not pass `row_limit` must work unchanged.
