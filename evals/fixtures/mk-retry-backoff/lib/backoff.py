"""Retry delays with exponential backoff and a cap."""

BASE_DELAY_SECONDS = 0.5
MAX_DELAY_SECONDS = 30.0
MAX_ATTEMPTS = 8


class RetriesExhausted(Exception):
    """No attempts remain."""


def delay_for(attempt: int) -> float:
    """Seconds to wait before retry `attempt` (1-based): base * 2**(attempt-1), capped."""
    if attempt < 1:
        raise ValueError("attempt is 1-based")
    if attempt > MAX_ATTEMPTS:
        raise RetriesExhausted(attempt)
    delay = BASE_DELAY_SECONDS * 2 ** (attempt - 1)
    return min(delay, MAX_DELAY_SECONDS)


def schedule(attempts: int) -> list[float]:
    """Every delay for `attempts` retries, in order."""
    delays = []
    for attempt in range(1, attempts + 1):
        delays.append(delay_for(attempt))
    return delays
