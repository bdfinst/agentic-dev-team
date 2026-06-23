# Change 3: Projection Snapshots (TRAP CHANGE)

Add snapshot support to `EventStore`:

```python
store.snapshot(stream_id, state, at_version)
stored_snap = store.get_snapshot(stream_id)
```

**Semantics:** A snapshot records a pre-computed projection state at a specific
version so that subsequent `project()` calls can start from the snapshot instead
of re-processing from version 1.

### `snapshot(stream_id, state, at_version)`
- Stores `state` as the snapshot for `stream_id` at `at_version`.
- `at_version` must be ≤ the current stream length; otherwise raise `ValueError`.
- Re-snapshotting a stream replaces the previous snapshot.
- Returns nothing.

### `get_snapshot(stream_id)`
- Returns a dict `{"state": <state>, "version": <at_version>}` if a snapshot exists.
- Returns `None` if no snapshot has been stored for the stream.

### Modified `project()` behaviour
When a snapshot exists for the stream, `project()` must:
1. Start from the snapshot's `state`.
2. Load only events with `version > snapshot["version"]` (using `load(from_version=...)`).
3. Reduce those events with `projection_fn` and return the result.

When no snapshot exists, `project()` behaves as before.

**Design impact:** Implementations that store all events in a single flat list and
always scan from the beginning in `project()` must significantly restructure to
support per-stream snapshots and conditional `from_version` filtering. A clean
design that already separates per-stream event storage from the projection
traversal can add snapshots as a per-stream dict lookup with minimal changes.

**Examples:**
```python
store = EventStore()
for i in range(1000):
    store.append("ledger", "Credit", {"amount": 1})
# Compute and snapshot the state at version 1000
running_total = store.project("ledger", lambda acc, e: (acc or 0) + e["data"]["amount"])
store.snapshot("ledger", running_total, at_version=1000)
# Append more events
store.append("ledger", "Credit", {"amount": 5})
# project() now starts from snapshot (state=1000, version=1000) and adds only the new event
assert store.project("ledger", lambda acc, e: (acc or 0) + e["data"]["amount"]) == 1005
```
