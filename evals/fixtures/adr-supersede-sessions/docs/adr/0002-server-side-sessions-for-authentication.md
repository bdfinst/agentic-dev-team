# 2. Server-side sessions for authentication

Date: 2025-03-20

## Status

Accepted

## Context

The only client is the server-rendered web app. Sessions must be revocable
immediately when an account is locked.

## Decision

Authenticate with an opaque session ID in an HttpOnly cookie. Session state
lives in the `sessions` table and is checked on every request.

## Consequences

Instant revocation. Every request reads the `sessions` table.
