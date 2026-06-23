# Event Store

Build an `EventStore` class in `event_store.py` that stores events organised by
stream and allows projecting them into application state.

## Public API

```python
from event_store import EventStore, OptimisticConcurrencyError

store = EventStore()
store.append(stream_id, event_type, data)
events = store.load(stream_id)
state = store.project(stream_id, projection_fn)
```

### Events
An event is a dict with at least:
- `"stream_id"` (str)
- `"event_type"` (str)
- `"data"` (dict)
- `"version"` (int): 1-based position within the stream

### `append(stream_id, event_type, data)`
- Appends a new event to the named stream.
- Returns the event dict as stored.

### `load(stream_id)`
- Returns a list of all events in the stream, in append order.
- Non-existent stream returns `[]`.

### `project(stream_id, projection_fn)`
- Calls `projection_fn(state, event)` for each event in order, starting from
  `state=None`, and returns the final state.
- Non-existent stream returns `None`.

### `OptimisticConcurrencyError`
- A custom exception (subclass of `Exception`) for version conflicts.
