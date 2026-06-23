# Notification Service

Build a `NotificationService` class in `notifier.py` that dispatches notifications
to recipients through registered channels.

## Public API

```python
from notifier import NotificationService

svc = NotificationService()
svc.register_channel(name, handler)
svc.send(recipient, message, channels=None)
results = svc.send_bulk(recipients, message, channels=None)
```

### Channel handlers
A channel handler is a callable:
```python
def handler(recipient: str, message: str) -> bool:
    ...  # return True if sent, False if failed
```

### Behaviour
- `register_channel(name, handler)` registers a channel by name.
- `send(recipient, message, channels=None)` dispatches the message to `recipient`
  via all registered channels (or only the listed `channels` if provided).
  Returns a dict mapping channel name → bool (True = sent).
- `send_bulk(recipients, message, channels=None)` sends to every recipient in the
  list. Returns a dict mapping each recipient → the per-channel result dict.
- Requesting a channel that was not registered raises `ValueError`.
- If a handler returns False, that is recorded but does not raise an exception.
