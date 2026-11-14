# 4. Outbound HTTP goes through infrastructure adapters

Status: Accepted

## Context

Checkout calls three partner APIs. Timeouts, retries and credentials were
handled differently at each call site, and use-case tests needed a live
network.

## Decision

Only modules under `src/infrastructure/http/` may make HTTP calls (`fetch`,
`axios`, or any other client). Every partner API gets a port interface in
`src/application/ports/` and an adapter in `src/infrastructure/http/` that
implements it. Use cases depend on the port.

## Consequences

Use cases are tested with in-memory port implementations. Timeouts, retries
and credentials live in one place per partner.
