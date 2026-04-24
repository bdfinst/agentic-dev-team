"""http_client — rate-limited, budget-tracked, audit-logged HTTP.

All harness HTTP traffic flows through the module-level `client` singleton.
Rate limiting uses an injectable `Clock` so tests are deterministic; production
uses the default `time.monotonic` clock.

Exposes:
    client.probe(url, method="GET", **kwargs) -> httpx.Response | None
    client.get(url, **kwargs)                 -> httpx.Response | None
    client.post_predict(payload)              -> httpx.Response | None
    client.total_queries: int                 (global counter)
    QueryBudgetExhausted                      (exception raised when budget hits 0)

Clock interface (for tests):
    class Clock:
        def now(self) -> float: ...
        def sleep(self, seconds: float) -> None: ...

Mock implementation:
    class MockClock:
        def __init__(self): self._t = 0.0
        def now(self): return self._t
        def sleep(self, seconds): self._t += seconds
        def advance(self, seconds): self._t += seconds  # explicit bump
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .. import config


class QueryBudgetExhausted(Exception):
    """Raised when config.QUERY_BUDGET is reached. Halts the pipeline."""


class Clock(Protocol):
    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass
class HTTPClient:
    clock: Clock = field(default_factory=SystemClock)
    total_queries: int = 0
    _last_request_ts: float = -1e9
    _session: httpx.Client | None = None

    def _ensure_session(self) -> httpx.Client:
        if self._session is None:
            self._session = httpx.Client(timeout=config.REQUEST_TIMEOUT)
        return self._session

    def _apply_rate_limit(self) -> None:
        if config.RATE_LIMIT <= 0:
            return
        min_interval = 1.0 / config.RATE_LIMIT
        elapsed = self.clock.now() - self._last_request_ts
        if elapsed < min_interval:
            self.clock.sleep(min_interval - elapsed)
        self._last_request_ts = self.clock.now()

    def _check_budget(self) -> None:
        if self.total_queries >= config.QUERY_BUDGET:
            raise QueryBudgetExhausted(
                f"Total query budget of {config.QUERY_BUDGET} reached; pipeline halted."
            )

    def _audit(self, method: str, url: str, status: int | None, error: str | None) -> None:
        record = {
            "ts": self.clock.now(),
            "method": method,
            "url": url,
            "status": status,
            "error": error,
            "total_queries": self.total_queries,
        }
        try:
            config.AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with config.AUDIT_LOG.open("a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            # Never let audit logging halt the pipeline. A missing audit is better
            # than a crashed probe.
            pass

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response | None:
        self._check_budget()
        self._apply_rate_limit()
        self.total_queries += 1

        session = self._ensure_session()
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = session.request(method, url, **kwargs)
                self._audit(method, url, resp.status_code, None)
                if resp.status_code >= 500 and attempt <= config.MAX_RETRIES:
                    self.clock.sleep(0.5 * attempt)
                    continue
                return resp
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                self._audit(method, url, None, type(e).__name__)
                if attempt > config.MAX_RETRIES:
                    return None
                self.clock.sleep(0.5 * attempt)

    # Public API

    def probe(self, url: str, method: str = "GET", **kwargs: Any) -> httpx.Response | None:
        """Low-level request. Use for recon / schema discovery."""
        return self._request(method, url, **kwargs)

    def get(self, url: str, **kwargs: Any) -> httpx.Response | None:
        return self._request("GET", url, **kwargs)

    def post_predict(self, payload: dict) -> httpx.Response | None:
        """POST payload to PREDICT_URL. Returns None on unrecoverable error."""
        return self._request(
            "POST",
            config.PREDICT_URL,
            json=payload,
            headers={"content-type": "application/json"},
        )


# Module-level singleton. Tests reset client.total_queries or create their own.
client = HTTPClient()
