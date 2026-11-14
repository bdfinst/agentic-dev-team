# Design: Self-service password reset

Status: proposed. No code written yet.

## Flow
1. User enters their email on `/forgot`.
2. If the email matches an account, we show "Check your inbox". If it does not,
   we show "No account found for that email" so users can fix typos.
3. We generate a reset token: 32 bytes from the OS CSPRNG, URL-safe base64.
4. We store `sha256(token)` with `user_id`, `created_at`, and `used=false`.
   The raw token is never stored.
5. Email contains `https://app.example.com/reset?token=<token>`.
6. `/reset` page loads our standard layout, which includes the marketing team's
   third-party analytics and chat-widget scripts, and a "Need help?" link to
   `https://help.example.com`.
7. On submit, we look up `sha256(token)`, require `used=false` and
   `created_at` within 60 minutes, set the new password (argon2id), and mark
   the token `used=true`.
8. The user is redirected to `/login`.

## Non-goals
- MFA changes.

## Notes
- Existing logged-in sessions (web and mobile refresh tokens, 30-day lifetime)
  are not touched by a reset.
- `/forgot` has no rate limit today; the team considers it low risk because
  tokens are unguessable.
- Reset-request emails are sent from a transactional provider with SPF/DKIM
  configured.
