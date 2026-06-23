# Change 2: Per-Channel Retry (TRAP CHANGE)

Add per-channel retry configuration to `register_channel`:

```python
svc.register_channel(name, handler, priority=0, fallback_for=None, max_retries=0)
```

**Semantics:** If `max_retries=N` (N ≥ 1), a handler that returns `False` or raises
is retried up to `N` additional times (total attempts = N + 1) before the channel
is recorded as failed.

**Rules:**
- Retry only on `False` return or exception — a `True` return stops retrying
  immediately.
- The first successful attempt records the channel as `True`.
- All `N` retries failing records the channel as `False`.
- `max_retries=0` (the default) means no retry — existing behaviour is preserved.
- Retries call the same handler with the same `(recipient, message)` arguments.
- Exception from a retry attempt is treated as `False` (not re-raised), and
  retrying continues.

**Design impact:** implementations that bake channel invocation logic into `send()`
as a flat loop must restructure to accommodate per-channel retry policies. A clean
design where each registered channel carries its own invocation policy (including
retry count) can add `max_retries` as a channel attribute and update only the
single dispatch call site.

**Examples:**
```python
attempts = []
def flaky(r, m):
    attempts.append(1)
    return len(attempts) >= 3  # succeeds on 3rd attempt

svc.register_channel("email", flaky, max_retries=2)
result = svc.send("alice", "hi")
# result = {"email": True}   (succeeded on 3rd attempt)
# len(attempts) == 3
```
