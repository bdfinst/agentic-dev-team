#!/usr/bin/env bash
# static-scan-on-edit.sh — PostToolUse hook for the agentic-security-review plugin.
#
# Fires on Edit/Write of security-relevant files. Dispatches to fast-tier
# tools based on file extension. Default severity threshold: error. Set
# `verbose_hooks: true` at the root of .claude/settings.local.json (or the
# project's local settings) to surface warnings.
#
# Opt out entirely by removing the Edit|Write matcher from the plugin's
# settings.local.json PostToolUse block.
#
# Input:  JSON on stdin with tool_input.file_path
# Output: Findings on stdout (shown to the user); exit 0 always (advisory).

set -uo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)

# No file path → not an Edit/Write we care about
[ -z "$FILE_PATH" ] && exit 0
[ ! -f "$FILE_PATH" ] && exit 0

# Verbose mode via settings.local.json — detect once per invocation
VERBOSE="false"
for settings in "./.claude/settings.local.json" "$HOME/.claude/settings.local.json"; do
  if [ -f "$settings" ]; then
    if jq -e '.verbose_hooks == true' "$settings" >/dev/null 2>&1; then
      VERBOSE="true"
      break
    fi
  fi
done

FILENAME="$(basename "$FILE_PATH")"
EXT="${FILE_PATH##*.}"
LOWER_EXT=$(echo "$EXT" | tr '[:upper:]' '[:lower:]')

# Severity threshold: error by default; include warnings in verbose mode
severity_ok() {
  local level="$1"
  if [ "$VERBOSE" = "true" ]; then
    return 0  # show all
  fi
  [ "$level" = "error" ]
}

print_finding() {
  local tool="$1" level="$2" file="$3" line="$4" msg="$5"
  severity_ok "$level" || return 0
  echo "  [hook/$tool] $level: $file:$line  $msg"
}

# ─── gitleaks on any file likely to carry secrets ─────────────────────────────
run_gitleaks() {
  command -v gitleaks >/dev/null 2>&1 || return 0
  local tmp
  tmp=$(mktemp)
  if gitleaks detect --no-git --source "$FILE_PATH" --report-format json --report-path "$tmp" 2>/dev/null; then
    local count
    count=$(jq 'length' "$tmp" 2>/dev/null || echo 0)
    if [ "$count" != "0" ]; then
      jq -r '.[] | "\(.RuleID // .Description) at :\(.StartLine)"' "$tmp" 2>/dev/null | while read -r line; do
        print_finding "gitleaks" "error" "$FILE_PATH" "?" "$line"
      done
    fi
  fi
  rm -f "$tmp"
}

# ─── hadolint on Dockerfile writes ───────────────────────────────────────────
run_hadolint() {
  command -v hadolint >/dev/null 2>&1 || return 0
  local out
  out=$(hadolint --format tty "$FILE_PATH" 2>&1 || true)
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    # hadolint output: "<file>:<line> <severity> ..."
    if echo "$line" | grep -qE "^.*:[0-9]+ (error|warning) "; then
      local level
      if echo "$line" | grep -q " error "; then level="error"; else level="warning"; fi
      print_finding "hadolint" "$level" "$FILE_PATH" "?" "$line"
    fi
  done <<< "$out"
}

# ─── actionlint on workflow files ────────────────────────────────────────────
run_actionlint() {
  command -v actionlint >/dev/null 2>&1 || return 0
  local out
  out=$(actionlint "$FILE_PATH" 2>&1 || true)
  if [ -n "$out" ]; then
    # actionlint defaults to warnings; surface in verbose mode
    print_finding "actionlint" "warning" "$FILE_PATH" "?" "see output below"
    if [ "$VERBOSE" = "true" ]; then
      echo "$out" | head -10 | sed 's/^/    /'
    fi
  fi
}

# ─── semgrep quick profile for code files ───────────────────────────────────
run_semgrep_quick() {
  command -v semgrep >/dev/null 2>&1 || return 0
  local tmp
  tmp=$(mktemp)
  # p/security-audit is a fast, widely-applicable bundle
  semgrep --quiet --severity ERROR --json --config p/security-audit \
    "$FILE_PATH" > "$tmp" 2>/dev/null || true
  local count
  count=$(jq '.results | length' "$tmp" 2>/dev/null || echo 0)
  if [ "$count" != "0" ]; then
    jq -r '.results[] | "\(.check_id) at \(.start.line): \(.extra.message)"' "$tmp" 2>/dev/null | while read -r line; do
      print_finding "semgrep" "error" "$FILE_PATH" "?" "$line"
    done
  fi
  rm -f "$tmp"
}

# ─── Dispatch by filename / extension ─────────────────────────────────────────
case "$FILENAME" in
  Dockerfile*|*.dockerfile)
    run_hadolint
    ;;
esac

case "$FILE_PATH" in
  */.github/workflows/*.yml|*/.github/workflows/*.yaml)
    run_actionlint
    ;;
esac

case "$LOWER_EXT" in
  env|example|local|staging|production|test|development)
    run_gitleaks
    ;;
esac

# Secret-bearing file names regardless of extension
case "$FILENAME" in
  .env*|*.pem|*.key|*credential*|*secret*|*.token)
    run_gitleaks
    ;;
esac

# Code files: semgrep quick pass
case "$LOWER_EXT" in
  py|js|jsx|ts|tsx|go|java|rb)
    run_semgrep_quick
    ;;
esac

exit 0
