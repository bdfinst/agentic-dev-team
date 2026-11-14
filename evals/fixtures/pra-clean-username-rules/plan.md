# Plan: Username validation on sign-up

**Created**: 2026-11-04
**Branch**: feat/username-rules
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

Sign-up accepts any username today, so 212 accounts hold names with spaces or
emoji that break profile URLs. Enforce the documented username rules at the
`POST /signup` endpoint. Existing accounts are out of scope.

## Acceptance Criteria

- [ ] AC1: A username of 3 to 20 characters drawn only from `a-z`, `0-9`, and `_` is accepted and the account is created (HTTP 201).
- [ ] AC2: A username of 2 characters or 21 characters is rejected with HTTP 422 and error code `USERNAME_LENGTH`; no account is created.
- [ ] AC3: A username containing any character outside `a-z`, `0-9`, `_` (including upper case and spaces) is rejected with HTTP 422 and error code `USERNAME_CHARSET`; no account is created.
- [ ] AC4: A username that matches an existing username is rejected with HTTP 409 and error code `USERNAME_TAKEN`; the existing account is unchanged.

## Slices

### Slice 1: Username rules at sign-up

**Depends-on:** none
**Files:** `api/signup/validate.py`, `api/signup/handler.py`, `tests/signup/test_username.py`

**Behavior:**

```gherkin
Feature: Username rules at sign-up

  Scenario Outline: Usernames at the accepted length boundaries
    # Still passes if: the 201 body omits the new account id
    Given no account named "<name>" exists
    When a visitor signs up with username "<name>"
    Then the response status is 201
    And an account named "<name>" exists

    Examples:
      | name                 |
      | abc                  |
      | abcdefghij_012345678 |

  Scenario Outline: Usernames just outside the length boundaries
    # Still passes if: the 422 body omits the human-readable message
    Given no account named "<name>" exists
    When a visitor signs up with username "<name>"
    Then the response status is 422
    And the error code is "USERNAME_LENGTH"
    And no account named "<name>" exists

    Examples:
      | name                  |
      | ab                    |
      | abcdefghij_0123456789 |

  Scenario: Disallowed character is rejected
    # Still passes if: the charset check runs before the length check
    Given no account named "Bad Name" exists
    When a visitor signs up with username "Bad Name"
    Then the response status is 422
    And the error code is "USERNAME_CHARSET"
    And no account named "Bad Name" exists

  Scenario: Taken username is rejected
    # Still passes if: the comparison of names is case-insensitive
    Given an account named "dana_k" with email "dana@example.com" exists
    When a visitor signs up with username "dana_k" and email "other@example.com"
    Then the response status is 409
    And the error code is "USERNAME_TAKEN"
    And the account "dana_k" still has email "dana@example.com"
```

**Steps:**

#### Step 1.1: Length and charset rules

**Complexity**: standard
**IMPLEMENT**: Write `validate_username(name)` returning `None` or the error code `USERNAME_LENGTH` / `USERNAME_CHARSET`
**TEST**: Table test over lengths 2, 3, 20, 21 and names `Bad Name`, `DANA`, `dana!`, `dana_1`; assert the exact error code for each
**REFACTOR**: Compile the charset regex once at module level
**Files**: `api/signup/validate.py`, `tests/signup/test_username.py`
**Covers**: AC1, AC2, AC3
**Commit**: `feat(signup): validate username length and charset`

#### Step 1.2: Wire validation and uniqueness into the handler

**Complexity**: standard
**IMPLEMENT**: Call `validate_username` in the sign-up handler (422 + code on failure); return 409 `USERNAME_TAKEN` when the name exists
**TEST**: Handler-level tests: 201 creates the account; 422 and 409 create nothing and leave the existing account's email unchanged
**REFACTOR**: Map error codes to statuses in one table
**Files**: `api/signup/handler.py`, `tests/signup/test_username.py`
**Covers**: AC1, AC2, AC3, AC4
**Commit**: `feat(signup): reject invalid and taken usernames`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |

## Pre-PR Quality Gate

- [ ] All tests pass
- [ ] Linter passes
- [ ] `/code-review` passes

## Risks & Open Questions

- Two simultaneous sign-ups with the same name rely on the existing unique index on `users.username`; no new code path.
