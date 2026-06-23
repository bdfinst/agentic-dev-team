# Change 3: Streaming Render (TRAP CHANGE)

Add a `render_stream()` method to `ReportRenderer`:

```python
chunks = renderer.render_stream(data, format_name, **options)
```

**Semantics:** `render_stream()` returns an **iterator** (or generator) that yields
string chunks of the rendered output. The full concatenation of all chunks must
equal what `render()` would return.

**Handler upgrade path:** Format handlers may optionally implement streaming by
accepting a `_stream=True` keyword argument. If a handler does NOT accept
`_stream`, the renderer falls back to calling `render()` and yielding the full
string as a single chunk.

**Rules:**
- `render_stream()` must return an iterable; each element is a non-empty string
  (the renderer may filter empty chunks but must not split across multi-byte chars).
- `render_stream()` for an unknown format raises `ValueError` (same as `render()`).
- Existing `render()` behaviour is unchanged.

**Design impact:** Implementations that store handler return values as strings have
no streaming interface to plug into. A clean design that separates the handler
registry from the invocation path can add streaming as an alternative invocation
mode with minimal changes to the registry itself.

**Example:**
```python
renderer.register_format("csv", csv_handler)
for chunk in renderer.render_stream(data, "csv"):
    print(chunk, end="")
```
