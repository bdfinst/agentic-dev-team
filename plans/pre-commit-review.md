# Plan: Automated Pre-Commit Code Review

**Created**: 2026-04-02
**Branch**: main
**Status**: approved
**Spec**: [docs/specs/pre-commit-review.md](../docs/specs/pre-commit-review.md)

## Goal

Automate the `/code-review --changed` flow as a pre-commit gate using Claude Code's `PreToolUse` hook system and a temp file gate (`.review-passed`). Every commit is reviewed before it enters git history. The hook blocks `git commit` until a passing review exists for the exact set of staged files.

## Acceptance Criteria

- [ ] `PreToolUse` hook on `Bash` detects `git commit` and blocks (exit 2) when no valid `.review-passed` exists
- [ ] Hook computes hash of staged file paths and compares to `.review-passed` contents
- [ ] `/code-review --changed` writes `.review-passed` with staged-file hash on pass or warn
- [ ] Commit proceeds on second attempt when hash matches
- [ ] Staging new files after review invalidates the gate (hash mismatch)
- [ ] `.review-passed` is deleted after successful commit
- [ ] `.review-passed` is in `.gitignore`
- [ ] `git commit --no-verify` bypasses the gate
- [ ] Old advisory-only `pre-commit-review.sh` is replaced
- [ ] All changed files are checked, not just JS/TS

## Steps

### Step 1: Rewrite `hooks/pre-commit-review.sh` as a blocking gate

**Complexity**: standard
**RED**: Write a test that invokes the hook with a mock `git commit` command on stdin and verifies it exits 2 when no `.review-passed` file exists. Write a second test that creates a `.review-passed` file with the correct hash and verifies the hook exits 0.
**GREEN**: Rewrite `hooks/pre-commit-review.sh` to:
  1. Parse stdin JSON for `tool_input.command`
  2. Check if command matches `git commit` (but not `git commit --no-verify`)
  3. Compute hash: `git diff --cached --name-only | sort | shasum -a 256 | cut -d' ' -f1`
  4. If `.review-passed` exists and contents match hash → exit 0 (allow), delete `.review-passed`
  5. If no match → exit 2 with message: "BLOCKED: Run /code-review --changed before committing. Staged files must pass review."
  6. If no staged files → exit 0 (nothing to review)
**REFACTOR**: None needed
**Files**: `hooks/pre-commit-review.sh`, `hooks/pre-commit-review.test.sh` (or inline validation)
**Commit**: `feat: rewrite pre-commit-review hook as blocking gate with temp file check`

### Step 2: Register the hook in `.claude/settings.json`

**Complexity**: trivial
**RED**: N/A — config change
**GREEN**: Add the pre-commit-review hook to the existing `PreToolUse` `Bash` matcher in `.claude/settings.json`
**REFACTOR**: None needed
**Files**: `.claude/settings.json`
**Commit**: `feat: register pre-commit-review as PreToolUse Bash hook`

### Step 3: Update `/code-review` to write `.review-passed` on pass/warn

**Complexity**: standard
**RED**: Verify that after running `/code-review --changed` with a passing result, a `.review-passed` file exists with the correct hash of staged files.
**GREEN**: Add a final step to `commands/code-review.md` (after step 6): when the review overall status is `pass` or `warn` and `--changed` flag was used, compute the staged-file hash and write it to `.review-passed`.
**REFACTOR**: None needed
**Files**: `commands/code-review.md`
**Commit**: `feat: write .review-passed gate file on passing review`

### Step 4: Add `.review-passed` to `.gitignore`

**Complexity**: trivial
**RED**: N/A — config change
**GREEN**: Add `.review-passed` to `.gitignore`
**REFACTOR**: None needed
**Files**: `.gitignore`
**Commit**: `chore: add .review-passed to gitignore`

### Step 5: Document the pre-commit review gate

**Complexity**: trivial
**RED**: N/A — documentation
**GREEN**: Update README.md to mention the automated pre-commit review under the workflow section. Note the bypass mechanism (`--no-verify`).
**REFACTOR**: None needed
**Files**: `README.md`
**Commit**: `docs: document automated pre-commit review gate`

## Pre-PR Quality Gate

- [ ] Hook correctly blocks `git commit` when `.review-passed` is missing
- [ ] Hook correctly allows `git commit` when `.review-passed` hash matches
- [ ] Hook ignores non-commit Bash commands
- [ ] `/code-review --changed` writes `.review-passed` on pass/warn
- [ ] `.review-passed` is cleaned up after commit
- [ ] `/code-review --changed` passes
- [ ] Documentation updated

## Risks & Open Questions

- **Risk**: The hook fires on every `Bash` call — it must quickly exit 0 for non-commit commands to avoid slowing down all shell operations. **Mitigation**: First line checks if command contains `git commit`; if not, exit 0 immediately.
- **Risk**: `shasum` command name varies across platforms (`shasum` on macOS, `sha256sum` on some Linux). **Mitigation**: Try `shasum -a 256` first, fall back to `sha256sum`.
- **Risk**: The `.review-passed` file could become stale if a review passes but the user never commits. **Mitigation**: Harmless — the hash check ensures it only matches the exact staged files. A stale file with wrong hash is equivalent to no file.
- **Open question**: Should the hook also delete `.review-passed` on failed commit attempts (e.g., commit-msg hook rejects)? Recommend no — let the hash validation handle staleness naturally.
