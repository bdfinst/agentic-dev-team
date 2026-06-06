#!/usr/bin/env bash
# telemetry.sh — opt-in, privacy-clean telemetry beacon (issue #106).
#
# The plugin enforces observability on its targets but has none of its own. This
# records MINIMAL local events so the author can see which commands/skills get
# used and how often the pre-commit review gate is bypassed. It is one hook
# registered on multiple events; it branches on hook_event_name:
#
#   UserPromptSubmit  -> a slash command/skill was invoked: record its NAME only
#   PreToolUse (Bash) -> a `git commit`: record the review gate as fired, or
#                        BYPASSED when --no-verify is present
#
# PRIVACY: records only an event type, a command/gate NAME (matched to the
# slash-command grammar, never free text), an outcome, and the plugin version.
# No prompts, no command strings, no file paths, no code, no payloads.
#
# CONSENT: OFF by default. Enable with DEV_TEAM_TELEMETRY=on, or a
# <cwd>/.claude/telemetry.json containing {"enabled": true}. When off, nothing
# is recorded and nothing leaves the machine.
#
# TRANSPORT: local-only. Events append to <cwd>/metrics/telemetry.jsonl. There
# is no network egress in this implementation by design.
#
# Posture: record-only, fail-open. Never blocks; any error -> exit 0.

set -uo pipefail

input=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
echo "$input" | jq -e . >/dev/null 2>&1 || exit 0

cwd=$(echo "$input" | jq -r '.cwd // empty')
[ -n "$cwd" ] && [ -d "$cwd" ] || cwd="$PWD"

# --- consent gate (default OFF) ------------------------------------------------
enabled="off"
if [ "${DEV_TEAM_TELEMETRY:-}" = "on" ]; then
  enabled="on"
elif [ -f "${cwd}/.claude/telemetry.json" ]; then
  if jq -e '.enabled == true' "${cwd}/.claude/telemetry.json" >/dev/null 2>&1; then
    enabled="on"
  fi
fi
[ "$enabled" = "on" ] || exit 0

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
version=$(jq -r '.version // "unknown"' "${HOOK_DIR}/../.claude-plugin/plugin.json" 2>/dev/null || echo unknown)
log="${cwd}/metrics/telemetry.jsonl"

_emit() {  # _emit <event> <name> <outcome>
  mkdir -p "$(dirname "$log")" 2>/dev/null || return 0
  jq -nc \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg event "$1" --arg name "$2" --arg outcome "$3" --arg v "$version" \
    '{ts:$ts, event:$event, name:$name, outcome:$outcome, plugin_version:$v}' \
    >> "$log" 2>/dev/null || true
}

event_name=$(echo "$input" | jq -r '.hook_event_name // empty')

case "$event_name" in
  UserPromptSubmit)
    prompt=$(echo "$input" | jq -r '.prompt // empty')
    # Only a leading slash-command token (grammar-matched), never free text.
    if [[ "$prompt" =~ ^/([a-zA-Z][a-zA-Z0-9_-]*) ]]; then
      _emit "command" "${BASH_REMATCH[1]}" "invoked"
    fi
    ;;
  PreToolUse)
    tool=$(echo "$input" | jq -r '.tool_name // empty')
    [ "$tool" = "Bash" ] || exit 0
    cmd=$(echo "$input" | jq -r '.tool_input.command // empty')
    if [[ "$cmd" == *"git commit"* ]]; then
      if [[ "$cmd" == *"--no-verify"* ]] || [[ "$cmd" == *" -n "* ]]; then
        _emit "gate" "pre-commit-review" "bypassed"
      else
        _emit "gate" "pre-commit-review" "fired"
      fi
    fi
    ;;
esac

exit 0
