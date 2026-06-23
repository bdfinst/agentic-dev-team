# Report Renderer

Build a `ReportRenderer` class in `report_render.py` that renders tabular data into
different output formats via registered format handlers.

## Public API

```python
from report_render import ReportRenderer

renderer = ReportRenderer()
renderer.register_format(name, handler)
output = renderer.render(data, format_name, **options)
names = renderer.available_formats()
```

### Data
`data` is a list of dicts, where each dict is a row and the keys are column names.

### Format handlers
A format handler is a callable:
```python
def handler(data: list[dict], **options) -> str:
    ...
```

### Behaviour
- `register_format(name, handler)` registers a format handler by name.
- `render(data, format_name, **options)` calls the registered handler and returns
  the string result.
- `available_formats()` returns a list of registered format names.
- Requesting an unknown format raises `ValueError`.
- Empty data (empty list) is valid input; handlers receive an empty list.
