#!/usr/bin/env bash
# pre-commit-detect.sh — shared `git commit` detection helper for
# PreToolUse:Bash hooks.
#
# Sourced (not executed) by:
#   - hooks/pre-commit-review.sh
#   - hooks/pre-commit-knowledge-index.sh
#
# Exposes:
#   _is_git_commit_invocation <bash_command_string>
#     Returns 0 (true) if the command is a `git commit` we should gate
#     on, 1 otherwise. Treats `--no-verify` as a bypass (returns 1) so
#     the standard git escape hatch keeps working.

# _is_git_commit_invocation <bash_command_string>
_is_git_commit_invocation() {
  local cmd="$1"
  # Must look like `git commit`...
  if ! echo "$cmd" | grep -qE -- '^[[:space:]]*git[[:space:]]+commit\b'; then
    return 1
  fi
  # ...and not be the documented bypass. The `--` separator stops grep
  # from parsing `--no-verify` as a flag (which some grep variants would).
  if echo "$cmd" | grep -qE -- '--no-verify'; then
    return 1
  fi
  return 0
}
