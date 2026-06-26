# Spec: Password reset

## Acceptance criteria

1. A user can request a reset link by submitting their email.
2. The reset link expires 30 minutes after it is issued.
3. Submitting an unknown email returns the same generic response as a known
   email (no account enumeration).

## Scenarios

```gherkin
Scenario: Expired reset link is rejected
  Given a reset link issued 31 minutes ago
  When the user opens the link
  Then the reset is refused and a new link is offered
```

## Plan — files to change

- `src/reset.ts` — implement request + expiry.
- `tests/reset.test.ts` — cover all three criteria and the expiry scenario.
