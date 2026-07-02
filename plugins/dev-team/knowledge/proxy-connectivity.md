# Proxy Connectivity

## Root cause

Sessions that route Anthropic API traffic (or Bash-invoked tools like `curl`,
`dotnet restore`, `npm install`) through a corporate proxy can hit two
structurally different failure modes, both stemming from transient
corporate-proxy unavailability:

- **Connection refused** (this doc) — a transport-layer rejection. Nothing
  accepted the TCP connection at all.
- **Rate limited** (tracked separately in
  [issue #723](https://github.com/bdfinst/agentic-dev-team/issues/723)) — the
  proxy accepted the connection and the application layer returned an
  HTTP-level 429/503.

These require different responses (see below), so this file keeps them in
separate subsections rather than merging them into shared prose.

This mirrors the failure-mode taxonomy this repo already documents for
reviewed code under test — see the "Failure modes" bullet in
[`component-test-patterns.md`](component-test-patterns.md) (API Consumer
patterns) and the Polly-based resilience-policy coverage in
[`references/csharp-http-client-testing.md`](references/csharp-http-client-testing.md).
This doc applies that same taxonomy one level up, to the agent's own
session-level network behavior.

## Connection refused

**Signature:** `ECONNREFUSED` / "Connection refused" / any TCP-level
rejection — distinct from an HTTP-level 429/503 + `Retry-After`, which
requires the proxy to have accepted the connection in the first place. A
refused connection means nothing is listening/accepting on the other end:
commonly a proxy or network outage, a VPN drop, or a misconfigured proxy
address — not something the application layer can throttle its way out of.

**Policy:**

1. Retry a small, bounded number of times with backoff. Reuse the existing
   `DEV_TEAM_BASH_RETRY_THRESHOLD` default of `3` (see
   `hooks/bash_retry_guard.py`) as the reference retry count, for consistency
   with the one retry-count precedent already shipped in this plugin.
2. If the connection is still refused after those attempts, **stop** —
   do not keep retrying silently. Surface a concise diagnostic to the user
   that states:
   - what failed (the host/endpoint being reached, if known),
   - how many attempts were made,
   - that repeated refusal may indicate a proxy or network outage rather
     than a code problem, and remediation is likely outside the agent's
     control (e.g. check VPN/network status, confirm the proxy address,
     or contact whoever operates the proxy).

A rate limit is expected to clear on its own and warrants standard
exponential backoff (see #723); a refused connection may not clear on its
own, so spinning on it indefinitely stalls the session for no benefit.

**Non-goal:** this is documentation of expected agent behavior, not a new
hook. Reliably detecting "connection refused" from heterogeneous tool
stdout (curl, dotnet, npm, git, MCP clients each format it differently) is
not a safe, generically-matchable pattern for a `PreToolUse`/`PostToolUse`
hook without a high false-positive/false-negative rate, so this stays prose
guidance rather than mechanical enforcement.
