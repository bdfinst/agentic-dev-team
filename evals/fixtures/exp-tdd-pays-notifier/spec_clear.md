# Notification Service — Full Specification

Build a `NotificationService` class in `notifier.py` that dispatches notifications
to recipients through a registry of named channel handlers.

## Public API

```python
from notifier import NotificationService

svc = NotificationService()
svc.register_channel(name, handler, priority=0)
result  = svc.send(recipient, message, channels=None)
results = svc.send_bulk(recipients, message, channels=None)
```

### Channel handler protocol
A handler is any callable matching:
```python
def handler(recipient: str, message: str) -> bool:
    ...  # True = delivered, False = failed
```

### `register_channel(name, handler, priority=0)`
- Registers `handler` under `name`.
- `priority` (int, default 0): when `channels=None`, channels are tried in
  descending priority order (higher first); ties broken by registration order
  (first-registered first).
- Re-registering the same name replaces the existing handler and priority.

### `send(recipient, message, channels=None)`
- `channels=None`: use **all** registered channels, in priority-descending order.
- `channels=[...]`: use only the named channels, in the order listed.
  Raises `ValueError` if any name in the list is not registered.
- Calls each handler with `(recipient, message)`.
- A handler returning `False` is recorded as failed but **does not raise**.
- A handler that raises an exception is caught; the channel is recorded as failed
  (`False`) and the exception is **not re-raised**.
- Returns `dict[str, bool]` mapping channel name → delivery success.

### `send_bulk(recipients, message, channels=None)`
- Sends to every recipient in `recipients` using `send()`.
- Empty `recipients` → returns `{}` immediately (no dispatch).
- Returns `dict[str, dict[str, bool]]` mapping each recipient → their result dict.

## Module shape
Single file: `notifier.py` at the repo root. Export `NotificationService`.

## Edge-case decisions
- Duplicate channel name in `channels=[...]` → each name is called once (deduplicated,
  preserving first occurrence order).
- `channels=[]` (empty list) → no channels called; returns `{}`.
- `message=""` (empty string) → valid; handlers are called with the empty string.
- Handler that raises → caught; recorded as `False`; other channels still run.

## Acceptance scenarios (≥ 8)

1. Register one channel, send → handler called, result `{channel: True}`
2. Handler returning False → result `{channel: False}`, no exception raised
3. Unregistered channel in `channels=[...]` → `ValueError`
4. Two channels registered, `channels=None` → both called
5. Two channels, explicit `channels=["email"]` → only email handler called
6. send_bulk with two recipients → each recipient dispatched individually
7. send_bulk with empty recipients list → returns `{}`
8. Priority ordering: high-priority channel attempted before low-priority when
   `channels=None`
9. Handler that raises → recorded False, other channels still run
10. Duplicate channel name in `channels=[...]` → handler called only once
