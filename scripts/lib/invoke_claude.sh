#!/usr/bin/env bash
# invoke_claude.sh — headless Claude invocation for a specific pipeline phase.
#
# Wraps `claude -p <prompt>` to execute a named agent specification against
# given inputs, with authentication + availability detection and file-
# existence verification (instead of parsing the agent's textual response).
#
# Usage:
#   invoke_claude.sh <phase-label> <expected-output-file> <prompt-file-or-stdin>
#
#     <phase-label>          e.g. "phase-0-recon-fraud-scoring" — used in log
#                            messages + cache key
#     <expected-output-file> path that Claude is expected to have created
#                            when the call succeeds
#     <prompt-file-or-stdin> path to a file containing the prompt, OR "-" to
#                            read prompt from stdin
#
# Exit codes:
#   0  — expected output file exists after the call (success)
#   2  — claude CLI not on PATH
#   3  — claude call failed (non-zero exit)
#   4  — claude call succeeded but expected output file was not produced
#
# The script prints the phase label + outcome to stderr for logging; the
# caller is responsible for interpreting exit codes.

set -uo pipefail

PHASE="${1:?usage: invoke_claude.sh <phase-label> <expected-output-file> <prompt-file-or->}"
EXPECTED="${2:?expected-output-file required}"
PROMPT_SRC="${3:?prompt file path or '-' for stdin}"

if ! command -v claude &>/dev/null; then
  printf '  [skip] %s: claude CLI not on PATH\n' "$PHASE" >&2
  exit 2
fi

# Load the prompt
if [[ "$PROMPT_SRC" == "-" ]]; then
  PROMPT=$(cat)
else
  if [[ ! -f "$PROMPT_SRC" ]]; then
    printf '  [error] %s: prompt file not found: %s\n' "$PHASE" "$PROMPT_SRC" >&2
    exit 3
  fi
  PROMPT=$(cat "$PROMPT_SRC")
fi

START_EPOCH=$(date -u +%s)
printf '  [llm]  %s: dispatching...\n' "$PHASE" >&2

# Claude writes to stdout; we capture but only surface on error.
# Use --allowedTools to ensure Claude has the tools it needs
# without prompting interactively.
LOG=$(mktemp -t invoke-claude-XXXXXX.log)
if ! claude -p "$PROMPT" \
    --allowedTools "Read Glob Grep Bash Edit Write Agent" \
    --allow-dangerously-skip-permissions \
    > "$LOG" 2>&1; then
  printf '  [error] %s: claude exited non-zero. Last 10 lines:\n' "$PHASE" >&2
  tail -10 "$LOG" >&2
  rm -f "$LOG"
  exit 3
fi

END_EPOCH=$(date -u +%s)
DURATION=$((END_EPOCH - START_EPOCH))

if [[ ! -f "$EXPECTED" ]]; then
  printf '  [error] %s: expected output not produced: %s (claude ran for %ds)\n' \
    "$PHASE" "$EXPECTED" "$DURATION" >&2
  printf '    last 10 lines of claude output:\n' >&2
  tail -10 "$LOG" | sed 's/^/      /' >&2
  rm -f "$LOG"
  exit 4
fi

printf '  [ok]   %s: produced %s in %ds\n' "$PHASE" "$EXPECTED" "$DURATION" >&2
rm -f "$LOG"
exit 0
