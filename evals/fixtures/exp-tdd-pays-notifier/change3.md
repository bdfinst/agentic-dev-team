# Change 3: Send Audit Log

Add an audit log to `NotificationService`:

```python
svc.get_audit_log()  # returns list of log entries
svc.clear_audit_log()
```

**Semantics:** Every send attempt — including retries and fallbacks — is appended to
an in-memory audit log. Each entry is a dict with at minimum these keys:

```python
{
    "recipient":  str,     # who was the target
    "channel":    str,     # which channel was attempted
    "message":    str,     # the message content
    "success":    bool,    # True if the attempt returned True
    "attempt":    int,     # 1-based attempt number (1 = first try, 2 = first retry, …)
}
```

**Rules:**
- One entry per handler call (so 3 attempts from `max_retries=2` → 3 log entries).
- `get_audit_log()` returns a list of entry dicts in chronological order (earliest
  first); the list is a snapshot (further sends do not mutate the returned list).
- `clear_audit_log()` empties the log; subsequent sends start a fresh log.
- The audit log persists across multiple `send()` / `send_bulk()` calls.
- Fallback attempts are also logged under the fallback channel name.
