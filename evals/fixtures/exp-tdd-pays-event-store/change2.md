# Change 2: Global Event Log

Add a `load_all()` method to `EventStore`:

```python
all_events = store.load_all()
```

**Semantics:** Returns a flat list of **all** events across **all** streams, ordered
by the time they were appended to the store (global insertion order, not per-stream
version order).

**Rules:**
- The global order is the order in which `append()` calls completed, regardless of
  stream.
- `load_all()` returns a list; it is a snapshot (appending after the call does not
  mutate the returned list).
- Each event dict in the list has all the same fields as `load()` returns (including
  `metadata` from Change 1 if implemented).
- An empty store → `[]`.
- The per-stream `load()` and `project()` methods are unaffected.
