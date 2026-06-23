# Report Renderer — Full Specification

Build a `ReportRenderer` class in `report_render.py` that renders tabular data
into different output formats through a pluggable handler registry.

## Public API

```python
from report_render import ReportRenderer

renderer = ReportRenderer()
renderer.register_format(name, handler)
output: str = renderer.render(data, format_name, **options)
names: list[str] = renderer.available_formats()
```

### Data
`data` is a list of dicts. Each dict is one row; keys are column names. All rows in
a single render call share the same schema (same keys). Column order is the
insertion order of the keys in the first row.

### Format handler protocol
```python
def handler(data: list[dict], **options) -> str:
    ...
```
- Called with the full data list and any keyword options from `render()`.
- Must return a string.
- Handlers may not mutate the data list or its dicts.

### `register_format(name, handler)`
- Registers `handler` under `name`.
- Re-registering the same name replaces the existing handler.

### `render(data, format_name, **options)`
- Calls `handler(data, **options)` for the named format.
- Returns the string returned by the handler.
- Raises `ValueError` if `format_name` is not registered.
- Does **not** catch exceptions raised by handlers — let them propagate.

### `available_formats()`
- Returns a list of registered format names (any stable order).

## Module shape
Single file: `report_render.py` at the repo root. Export `ReportRenderer`.

## Edge-case decisions
- `data=[]` → handler is called with an empty list; the return value is whatever
  the handler produces (typically an empty string or header-only row).
- `None` values in row dicts → handler receives them as-is; the renderer does not
  filter or coerce.
- Unknown format → `ValueError` (not `KeyError`).
- Options not understood by a handler → the handler decides what to do
  (renderer passes them through unchanged).
- Column order: derived from `data[0].keys()` order; if `data=[]`, no columns.

## Acceptance scenarios (≥ 8)

1. Register a format, call render → handler is called and its string is returned
2. Unknown format raises `ValueError`
3. `available_formats()` returns registered names
4. Re-registering a format name replaces the old handler
5. Empty data list → handler called with `[]`, result returned (no error)
6. Options are forwarded to the handler: `render(data, "csv", delimiter=";")`
7. Column order follows first-row key order
8. `None` value in a row dict → passed to handler as-is (renderer does not stringify)
9. Handler exception propagates out of `render()` unchanged
10. Two formats registered → both appear in `available_formats()`
