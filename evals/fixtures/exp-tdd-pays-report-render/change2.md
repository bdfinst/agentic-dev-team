# Change 2: Format Aliases

Add `register_alias(alias, existing_format)` to `ReportRenderer`:

```python
renderer.register_alias(alias, existing_format)
```

**Semantics:** An alias is an alternative name for an already-registered format.
Calling `render(data, alias, **options)` is exactly equivalent to calling
`render(data, existing_format, **options)` — the same handler runs with the same
options.

**Rules:**
- `existing_format` must already be registered; otherwise raise `ValueError`.
- If `alias` collides with an existing format name (not just another alias), raise
  `ValueError` — a format name cannot be shadowed by an alias.
- `available_formats()` should include alias names alongside regular format names,
  clearly usable via `render()`.
- An alias may be aliased again (chaining is allowed, resolved to the ultimate
  handler).
- `register_format(alias_name, new_handler)` after `register_alias(alias_name, ...)`
  replaces the alias with a real format (the old alias mapping is discarded).

**Examples:**
```python
renderer.register_format("csv", csv_handler)
renderer.register_alias("comma", "csv")
result = renderer.render(data, "comma")  # calls csv_handler
```
