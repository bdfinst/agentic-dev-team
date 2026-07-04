---
name: proxy-resilience
description: Bounded backoff, retry ceiling, and escalation convention for repeated failures against a corporate Anthropic proxy. Use when you observe repeated HTTP 429 rate-limit responses or connection-refused errors that reference a proxy host, or the user says "proxy is rate-limiting", "429 from the proxy", "proxy connection refused", or "corporate proxy is flaky".
role: worker
user-invocable: true
---

# Proxy Resilience

## Overview

A corporate proxy fronting Anthropic API traffic enforces its own rate
limits and allowlist behavior, independent of the underlying account's tier
— a 429 or connection-refused error in a proxy-fronted session is a
different failure class than a direct-API rate limit (already retried
natively by the harness; do not apply this convention to those).

Covers two related failure modes sharing one root cause (transient
corporate-proxy unavailability) and one remedy shape (bounded backoff, a
hard retry ceiling, then escalate): rate-limit errors (issue #723, this
file) and connection-refused errors (issue #724). Documented together so
either failure mode is found in one place.

## Detection Signals

Treat an error as **proxy rate-limiting** when it shows *all* of:

1. The session is known to run against a corporate proxy (e.g. the
   `anthropic-proxy` operating note, a proxy env var/base URL, or a
   previously observed proxy hostname in error text).
2. The error text contains HTTP 429, "rate limit", "too many requests", or
   "quota exceeded".
3. The error references the proxy host, not `api.anthropic.com` directly.

Treat an error as **proxy connection-refused** (#724) when it shows (1)
above plus a connection-level failure (`ECONNREFUSED`, "connection
refused", "could not connect", timeout connecting to the proxy host).

## Backoff Schedule

Apply exponential backoff **per call site** (one place repeatedly issuing
the same request — e.g. one subagent retrying one API call, not the whole
session): **initial delay 1s, ×2 multiplier, 60s cap, max 5 attempts.**

| Attempt | 1 | 2 | 3 | 4 | 5 (last) |
|---------|---|---|---|---|---|
| Delay | 1s | 2s | 4s | 8s | 16s |

After 5 retries at the same call site still fail with a proxy rate-limit
error, stop retrying and escalate (below) rather than looping further. Five
is deliberately far below any plausible recurrence of "28 rate-limit errors
in one session" — that scale breaches this ceiling on the first call site
alone, well before reaching 28.

## Escalation Rule

Once the retry budget (5 attempts) is exhausted at a call site:

1. **Stop retrying that call site** — no indefinite loop, no silent failure.
2. Surface one plain-language line naming the proxy as the suspected cause,
   e.g.: "Repeated rate-limit errors from the corporate Anthropic proxy —
   pausing retries here; consider reducing concurrent requests or retrying
   later."
3. Let the user decide whether to continue, reduce concurrency, or pause.
   Escalate and wait for direction rather than unilaterally abandoning the
   task.

## Concurrency Guidance

Parallel subagent/Task fan-out against a shared proxy allowlist is a likely
amplifier of rate-limit bursts — concurrent requests can exhaust the
proxy's rate window faster than a serial stream would. If repeated 429s are
observed, reduce concurrent dispatch (e.g. lower
`DEV_TEAM_MAX_PARALLEL_BUILDS`, or serialize the specific failing call site)
before increasing backoff further; prefer narrow serialization over
session-wide serialization.

## Anti-Patterns

| Anti-pattern | Why it's wrong | What to do instead |
| ------------- | --------------- | ------------------- |
| Retrying immediately with no delay | Compounds the burst that triggered the 429 | Apply the backoff schedule above |
| Treating a direct Anthropic 429 the same as a proxy 429 | The harness already retries direct API limits; double-retrying wastes time | Confirm proxy involvement (Detection Signals) first |
| Increasing concurrency to "push through" a rate limit | Makes proxy throttling worse | Reduce concurrent dispatch instead |
