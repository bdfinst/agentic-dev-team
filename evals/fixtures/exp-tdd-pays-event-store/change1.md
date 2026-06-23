# Change 1: Event Metadata

Add an optional `metadata` parameter to `append`:

```python
store.append(stream_id, event_type, data, expected_version=None, metadata=None)
```

**Semantics:** `metadata` is an optional dict of supplementary information about the
event (e.g. correlation IDs, timestamps, user context). It is stored verbatim
alongside the event data and included in the returned event dict.

**Stored event shape (extended):**
```python
{
    "stream_id":   str,
    "event_type":  str,
    "data":        dict,
    "version":     int,
    "metadata":    dict or None,  # new field
}
```

**Rules:**
- `metadata=None` (the default) stores `None` in the metadata field.
- `metadata` is stored as-is; the store does not validate its contents.
- `load()` and `project()` return/use events with the `metadata` field included.
- Existing code that does not pass `metadata` must continue to work unchanged.
- The `metadata` field appears in the event dict regardless of whether it was
  supplied (set to `None` if not supplied, not absent).
