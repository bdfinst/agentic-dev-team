# Spec: Login lockout

## Acceptance criteria

1. A successful login with the correct password returns a session.
2. After 5 consecutive failed logins the account is locked.
3. A locked account refuses login, even with the correct password.
4. A successful login resets the failed-login count to zero.

## Scenarios

```gherkin
Scenario: Fifth wrong password locks the account
  Given an account with 4 consecutive failed logins
  When the user submits a wrong password
  Then the account is locked

Scenario: Locked account refuses the correct password
  Given a locked account
  When the user submits the correct password
  Then login is refused with reason "locked"
```

## Plan — files to change

- `src/lockout.ts` — implement login with the lockout rule.
- `tests/lockout.test.ts` — cover all four criteria and both scenarios.
