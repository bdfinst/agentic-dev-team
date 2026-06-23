# Event Store — Full Specification

Build an `EventStore` class in `event_store.py` that provides append-only, per-stream
event persistence with optimistic concurrency and arbitrary projections.

## Public API

```python
from event_store import EventStore, OptimisticConcurrencyError

store = EventStore()
stored  = store.append(stream_id, event_type, data, expected_version=None)
events  = store.load(stream_id, from_version=0)
state   = store.project(stream_id, projection_fn, initial_state=None)
```

### `OptimisticConcurrencyError(Exception)`
Custom exception; raised by `append()` on version conflict.

### Event shape
Each stored event is a dict with these keys:
```python
{
    "stream_id":   str,
    "event_type":  str,
    "data":        dict,  # caller-supplied; stored verbatim
    "version":     int,   # 1-based position within the stream
}
```

### `append(stream_id, event_type, data, expected_version=None)`
- `expected_version=None`: unconditional append (no concurrency check).
- `expected_version=N` (int): if the stream's current version (number of events
  already stored) ≠ N, raise `OptimisticConcurrencyError` before writing anything.
- On success, assigns the new event `version = current_length + 1` and stores it.
- Returns the stored event dict.

### `load(stream_id, from_version=0)`
- Returns events for the stream with `version > from_version`, in version order.
- `from_version=0` (default) → returns all events.
- Non-existent stream → returns `[]` (no exception).

### `project(stream_id, projection_fn, initial_state=None)`
- Reduces the stream using `projection_fn(state, event)` starting from `initial_state`.
- Events are processed in version order.
- Non-existent stream → returns `initial_state`.

## Module shape
Single file: `event_store.py` at the repo root. Export `EventStore` and
`OptimisticConcurrencyError`.

## Edge-case decisions
- Multiple streams are independent; versioning restarts at 1 per stream.
- `load()` returns a list of immutable snapshots — callers must not expect mutations
  to the returned dicts to affect stored state.
- `project()` with `initial_state=None` starts reduction from None (not `{}`).
- `expected_version=0` means the stream must currently be empty.
- Projection function that raises → exception propagates out of `project()`.

## Acceptance scenarios (≥ 8)

1. Append one event → returns event dict with `version=1`
2. Append two events to same stream → versions 1 and 2
3. Load non-existent stream → `[]`
4. Load after appending → events in append order
5. `expected_version=0` on empty stream → succeeds
6. `expected_version=0` on non-empty stream → `OptimisticConcurrencyError`
7. `expected_version=N` when current version is N → succeeds
8. `expected_version=N` when current version is N+1 → `OptimisticConcurrencyError`
9. project → reduction of events by projection function
10. project on non-existent stream → returns initial_state
11. `load(from_version=1)` returns only events with version > 1
12. Two independent streams: appending to one does not affect the other
