# Change 1: Fallback Channels

Add optional fallback support to `register_channel`:

```python
svc.register_channel(name, handler, priority=0, fallback_for=None)
```

**Semantics:** If `fallback_for="primary_channel_name"`, this channel becomes a
**fallback** for the named primary channel. When the primary channel's handler
returns `False` or raises an exception, the fallback channel is automatically
attempted for the same recipient and message.

**Rules:**
- A fallback is only tried if its primary fails (returns False or raises).
- The fallback result is merged into the send result dict under its own name.
- A fallback channel can itself be listed in `channels=[...]` — it is treated as a
  regular channel in that case.
- When `channels=None`, fallbacks are not in the normal channel list — they only
  run as fallbacks for their primary.
- A primary can have at most one registered fallback; re-registering replaces it.
- If the primary channel is not registered, `ValueError` is raised at
  `register_channel` time.

**Examples:**
```python
svc.register_channel("email", email_handler)
svc.register_channel("sms", sms_handler, fallback_for="email")

# email fails → sms is tried automatically
result = svc.send("alice", "hi")
# result = {"email": False, "sms": True}  (if email failed, sms succeeded)
# result = {"email": True}               (if email succeeded, sms not tried)
```
