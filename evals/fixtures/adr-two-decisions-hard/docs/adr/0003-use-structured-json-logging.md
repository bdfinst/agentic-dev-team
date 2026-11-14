# 3. Use structured JSON logging

Date: 2025-01-22

## Status

Accepted

## Context

Logs are shipped to a central store and queried by field.

## Decision

All services log one JSON object per line with `ts`, `level`, `msg`, and
`trace_id` fields.

## Consequences

Plain-text log lines are rejected in review.
