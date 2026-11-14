# Auth for the mobile apps (agreed 2025-09-02)

The iOS and Android apps launch in Q4. Cookies are awkward in the native HTTP
clients, and the `sessions` table read is now 30% of database load.

Decision: replace server-side sessions for ALL clients (web included, to keep
one code path) with signed JWT access tokens (15-minute lifetime) plus
rotating refresh tokens stored in a `refresh_tokens` table. Locking an account
revokes its refresh tokens; an already-issued access token stays valid for at
most 15 minutes. Security signed off on that 15-minute exposure window.

Alternatives rejected: keep cookies and add a mobile-only token path (two
auth systems to secure); long-lived JWTs with a deny-list (re-introduces the
per-request table read).

This replaces the sessions decision we recorded earlier.
