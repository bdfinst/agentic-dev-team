---
rules:
  - id: a-known-false-positive-in-tests
    rule_id: semgrep.python.hardcoded-credentials-test
    files:
      - "tests/**"
      - "spec/**"
    rationale: >
      Test fixtures include deliberately-hardcoded dummy credentials to drive
      auth-flow test cases. These paths are excluded from production bundles
      by the build config (verified: pyproject.toml excludes tests/ from the
      wheel). Suppressing prevents CI noise while real hardcoded creds remain
      caught in production source paths.
    expires: 2026-10-21
    owner: security-team
    scope: finding
    broad: false

  - id: b-unused-ruleid-on-purpose
    rule_id: semgrep.java.never-triggers-here
    files:
      - "src/**"
    rationale: >
      This rule exists to demonstrate that a rule which matches NO real finding
      is a no-op — not an error. It is retained in the fixture to keep the eval
      matrix honest.
    expires: 2027-01-01
    owner: eval-fixture-maintainer
    scope: finding
    broad: false
---

# Accepted Risks (fixture: matched)

This fixture declares two rules. Rule A matches the seeded finding at
`tests/auth_test.py:14`. Rule B matches nothing and exercises the no-op path.
