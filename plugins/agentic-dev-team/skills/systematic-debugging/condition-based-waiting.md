# Condition-Based Waiting

## When to Use

A test is flaky because it uses an arbitrary sleep or timeout (`sleep(5)`, `setTimeout(5000)`, `time.sleep(3)`). Too short and it fails intermittently; too long and it slows the suite.

## Problem

Arbitrary waits assume the operation takes a fixed amount of time. In practice, duration varies with system load, network conditions, CI runner speed, and data volume. The result is tests that pass locally but fail in CI, or pass most of the time but fail unpredictably.

## Solution: Poll for the Condition

Replace the fixed wait with a polling loop that checks whether the expected condition is true, with a timeout ceiling to prevent infinite hangs.

### Pattern (Pseudocode)

```
function waitFor(condition, timeoutMs, intervalMs):
    deadline = now() + timeoutMs
    while now() < deadline:
        if condition() is true:
            return success
        wait(intervalMs)
    fail("Timed out after {timeoutMs}ms waiting for: {description}")
```

### Key Decisions

- **Condition**: The specific assertion you are waiting for (element visible, row exists, queue empty, response received).
- **Timeout**: The maximum time you are willing to wait. Set this generously — it is a safety net, not the expected duration.
- **Interval**: How often to check. 50-200ms is typical for UI; 500-1000ms for backend operations.
- **Error message**: Include what you were waiting for. "Timed out after 10s" is useless; "Timed out after 10s waiting for order status to become SHIPPED" is actionable.

### Key Principle

Wait for the condition, not for time. The test should proceed the instant the condition is met and fail with a clear message if it never is.

### Common Applications

- DOM element appearing or disappearing
- Async API response completing
- Database record reaching expected state
- Background job finishing
- Event being emitted
