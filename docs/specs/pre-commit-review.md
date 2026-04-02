# Specification: Automated Pre-Commit Code Review

**Created**: 2026-04-02
**Status**: approved

## Intent Description

**What**: Run the `/code-review --changed` flow automatically before every commit, blocking the commit until review agents have passed. Uses a temp file gate — the review writes a `.review-passed` file with a hash of staged files, and the pre-commit hook only allows commits when the hash matches.

**Why**: Currently, code review only happens when explicitly invoked. Making it automatic ensures every commit has been reviewed, catching issues before they enter git history. Warnings are surfaced to the user at review time for a case-by-case decision rather than pre-configured as pass or block.

**Scope**: Pre-commit automation of the existing review flow only. Does not change `/code-review` itself, add new review agents, or modify the review output format.

## User-Facing Behavior

```gherkin
Feature: Automated pre-commit code review

  Scenario: First commit attempt is blocked with review instruction
    Given changed files are staged for commit
    And no .review-passed file exists for the current staged files
    When the user or agent attempts to commit
    Then the commit is blocked
    And the hook instructs Claude to run /code-review --changed

  Scenario: Commit proceeds after passing review
    Given Claude has run /code-review --changed and it returned pass or warn
    And a .review-passed file exists with a hash matching the staged files
    When the user or agent attempts to commit
    Then the commit proceeds normally
    And the .review-passed file is deleted after the commit

  Scenario: Commit remains blocked after failing review
    Given Claude has run /code-review --changed and it returned fail
    And no .review-passed file was written
    When the user or agent attempts to commit again
    Then the commit is blocked
    And the failure details are displayed

  Scenario: Staged files change after review passes
    Given a .review-passed file exists from a prior review
    And the user stages additional files after the review
    When the user or agent attempts to commit
    Then the commit is blocked because the staged file hash no longer matches
    And the hook instructs Claude to re-run /code-review --changed

  Scenario: Warnings are surfaced for human decision
    Given the review returned warn status
    When the review completes
    Then the warning details are displayed to the user
    And a .review-passed file is written (warnings do not block)
    And the user decides per-warning whether to fix or proceed

  Scenario: Review can be bypassed
    Given the user needs to commit without review
    When the user commits with --no-verify
    Then the commit proceeds without review
```

## Architecture Specification

**Components affected**:
1. `hooks/pre-commit-review.sh` — rewrite as a `PreToolUse` hook on `Bash` that detects `git commit` commands, checks for `.review-passed` with matching staged-file hash, blocks (exit 2) if missing, allows if matching
2. `.claude/settings.json` — add the new hook to `PreToolUse` matcher for `Bash`
3. `/code-review` command (`commands/code-review.md`) — add a step: when invoked with `--changed` and review passes (pass or warn), write `.review-passed` containing the hash of reviewed files
4. `.gitignore` — add `.review-passed`

**Gate mechanism**:
- Hash = sorted list of staged file paths piped through `shasum`
- `.review-passed` contains the hash string
- Hook computes hash of current staged files and compares to file contents
- Match → allow commit (exit 0). Mismatch or missing → block (exit 2)
- Post-commit: hook or commit success deletes `.review-passed`

**File scope**: The hook checks all staged files, not just JS/TS. The review agents themselves decide which files are relevant to their scope.

**Bypass**: `git commit --no-verify` skips all hooks including this one. This is the standard git bypass mechanism.

**Dependencies**:
- Claude Code `PreToolUse` hook system (exit 2 = block)
- `shasum` (available on macOS and Linux)
- Existing `/code-review --changed --json` command

## Acceptance Criteria

- [ ] A `PreToolUse` hook on `Bash` detects `git commit` commands and blocks them (exit 2) when no valid `.review-passed` file exists
- [ ] The hook computes a hash of staged file paths and compares to `.review-passed` contents
- [ ] `/code-review --changed` writes `.review-passed` with the staged-file hash when review returns pass or warn
- [ ] The commit proceeds on the second attempt when `.review-passed` hash matches staged files
- [ ] Staging new files after review invalidates the gate (hash mismatch → re-review required)
- [ ] `.review-passed` is deleted after a successful commit
- [ ] `.review-passed` is in `.gitignore`
- [ ] `git commit --no-verify` bypasses the review gate
- [ ] The old advisory-only `pre-commit-review.sh` is replaced
- [ ] All changed files are checked, not just JS/TS
