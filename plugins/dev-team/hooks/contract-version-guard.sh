#!/usr/bin/env bash
# contract-version-guard.sh — Claude Code PreToolUse hook
#
# Blocks Write/Edit operations that change the body of
# plugins/agentic-dev-team/knowledge/security-primitives-contract.md without
# also bumping the `version:` field in its YAML frontmatter.
#
# Semver policy (see the contract file for details):
#   PATCH = doc/typo; MINOR = additive; MAJOR = breaking.
#
# Bypass: release-please[bot] commits are allowed through (detected via
# GITHUB_ACTOR, GIT_AUTHOR_EMAIL, or GIT_AUTHOR_NAME matching the bot). Bypass
# is logged to metrics/contract-version-guard-audit.jsonl.
#
# Input:  JSON on stdin with tool_input.{file_path, content | new_string, old_string}
# Output: Message on stdout; exit 2 to block, exit 0 to allow.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CONTRACT_PATH="plugins/agentic-dev-team/knowledge/security-primitives-contract.md"
AUDIT_LOG="$REPO_ROOT/metrics/contract-version-guard-audit.jsonl"

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)

# Not targeting the contract — pass through.
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Normalize to repo-relative.
case "$FILE_PATH" in
  "$REPO_ROOT"/*) REL_PATH="${FILE_PATH#"$REPO_ROOT"/}" ;;
  /*) REL_PATH="$FILE_PATH" ;;
  *) REL_PATH="$FILE_PATH" ;;
esac

if [ "$REL_PATH" != "$CONTRACT_PATH" ]; then
  exit 0
fi

# ── Release-please bypass ────────────────────────────────────────────────────
log_bypass() {
  mkdir -p "$(dirname "$AUDIT_LOG")" 2>/dev/null || true
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local bypass_reason="$1"
  printf '{"ts":"%s","bypass":true,"reason":"%s","github_actor":"%s","git_email":"%s"}\n' \
    "$ts" "$bypass_reason" "${GITHUB_ACTOR:-}" "${GIT_AUTHOR_EMAIL:-}" \
    >> "$AUDIT_LOG" 2>/dev/null || true
}

is_release_please() {
  case "${GITHUB_ACTOR:-}" in
    *release-please*) return 0 ;;
  esac
  case "${GIT_AUTHOR_EMAIL:-}" in
    *release-please*) return 0 ;;
  esac
  case "${GIT_AUTHOR_NAME:-}" in
    *release-please*) return 0 ;;
  esac
  return 1
}

if is_release_please; then
  log_bypass "release-please-actor"
  exit 0
fi

# ── Extract proposed new content ─────────────────────────────────────────────
NEW_CONTENT=""
OLD_STRING=""
NEW_STRING=""

case "$TOOL_NAME" in
  Write)
    NEW_CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty' 2>/dev/null || true)
    ;;
  Edit)
    OLD_STRING=$(echo "$INPUT" | jq -r '.tool_input.old_string // empty' 2>/dev/null || true)
    NEW_STRING=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty' 2>/dev/null || true)
    ;;
esac

# Helper: extract `version:` from YAML frontmatter (first --- delimited block).
extract_version() {
  # Reads stdin, prints the version string (or empty).
  awk '
    /^---[[:space:]]*$/ {
      delim++
      if (delim == 2) exit
      next
    }
    delim == 1 && /^version:[[:space:]]/ {
      sub(/^version:[[:space:]]+/, "")
      gsub(/["\047[:space:]]/, "")
      print
      exit
    }
  '
}

# Helper: strip frontmatter and body-preamble whitespace for comparison.
body_digest() {
  awk '
    /^---[[:space:]]*$/ {
      delim++
      if (delim == 2) { in_body=1; next }
      next
    }
    in_body { print }
  ' | tr -s '[:space:]' ' '
}

# Fetch HEAD version of the contract, if available.
HEAD_CONTENT=""
if git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  HEAD_CONTENT=$(git -C "$REPO_ROOT" show "HEAD:$CONTRACT_PATH" 2>/dev/null || true)
fi

# If the file doesn't yet exist in HEAD, this is the initial add — require a
# non-empty version field but don't need a "bump."
if [ -z "$HEAD_CONTENT" ]; then
  if [ "$TOOL_NAME" = "Write" ]; then
    new_version=$(printf '%s' "$NEW_CONTENT" | extract_version)
    if [ -z "$new_version" ]; then
      echo "contract-version-guard: initial add of $CONTRACT_PATH must include a 'version:' field in frontmatter." >&2
      exit 2
    fi
  fi
  exit 0
fi

head_version=$(printf '%s' "$HEAD_CONTENT" | extract_version)

# For Edit: reconstruct the proposed new content by substituting old_string with new_string in HEAD.
if [ "$TOOL_NAME" = "Edit" ]; then
  if [ -z "$OLD_STRING" ] || [ -z "$NEW_STRING" ]; then
    # Unusual edit (e.g. replace_all empty) — be conservative and allow; let
    # other guards catch.
    exit 0
  fi
  # Only substitute first occurrence, per Edit semantics.
  NEW_CONTENT=$(printf '%s' "$HEAD_CONTENT" | awk -v old="$OLD_STRING" -v new="$NEW_STRING" '
    BEGIN { replaced=0 }
    {
      if (!replaced) {
        idx = index($0, old)
        if (idx > 0) {
          $0 = substr($0, 1, idx-1) new substr($0, idx + length(old))
          replaced = 1
        }
      }
      print
    }
  ')
fi

new_version=$(printf '%s' "$NEW_CONTENT" | extract_version)

if [ -z "$new_version" ]; then
  echo "contract-version-guard: proposed edit removes or blanks the 'version:' field. The contract MUST carry a semver version string." >&2
  exit 2
fi

# If body is unchanged, any version change (or no change) is fine.
head_body=$(printf '%s' "$HEAD_CONTENT" | body_digest)
new_body=$(printf '%s' "$NEW_CONTENT" | body_digest)

if [ "$head_body" = "$new_body" ]; then
  # Body unchanged — allow (could be a frontmatter-only edit, e.g. clarifying description).
  exit 0
fi

# Body changed. Require version bump.
if [ "$head_version" = "$new_version" ]; then
  cat >&2 <<EOF
contract-version-guard: edit to $CONTRACT_PATH changes the body without bumping 'version:'.

  current HEAD version: ${head_version:-<none>}
  proposed version:     $new_version

Per the contract's semver policy:
  - PATCH (${head_version} → next) for typos / clarifications / doc polish
  - MINOR (e.g. 1.x → 1.(x+1)) for additive changes (new optional fields, new enum values, new agent/skill IDs)
  - MAJOR (e.g. 1.y → 2.0.0) for breaking changes (renamed/removed fields, new required fields)

Bump the version to match your change, then retry the edit.
EOF
  exit 2
fi

# Body changed AND version is different — allow.
exit 0
