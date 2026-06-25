#!/usr/bin/env bash
# context-ceiling-guard.sh — PreToolUse hook (Agent + Skill).
#
# Enforces the 40% context-window ceiling from the Context Loading Protocol
# (CLAUDE.md "40% Context Window Rule"). Before a capability-loading call —
# an Agent dispatch or a Skill invocation — it reads the *real* context
# occupancy from the session transcript's most recent assistant-message usage
# (input + cache_read + cache_creation tokens) and compares it to the model's
# context window. Over the ceiling it nudges the orchestrator to summarize
# (warn, the default) or blocks the load (strict mode).
#
# Why occupancy from the transcript and not a self-estimate: the model has no
# reliable readout of its own context fill; the usage the harness recorded in
# the transcript is the ground truth.
#
# Posture: warn-by-default, fail-open. Like codegraph-nudge.sh it writes the
# message to stderr and exits 0 to allow/warn, exit 2 to block. Any error,
# unmatched tool, or unmeasurable context → exit 0 — a measurement failure
# never blocks a session.
#
# Recovery skills are never gated: blocking /context-summarization (the way
# back under budget) would deadlock the session.
#
# Env:
#   DEV_TEAM_CONTEXT_CEILING=off     disable entirely (default on)
#   DEV_TEAM_CONTEXT_STRICT=on       block over the ceiling (default: warn only)
#   DEV_TEAM_CONTEXT_CEILING_PCT=N   ceiling percent (default 40)
#   DEV_TEAM_CONTEXT_WINDOW=N        context window in tokens. Defaults to
#                                    200000 (every current Claude model's base
#                                    window). The transcript omits the [1m]
#                                    suffix, so a 1M-context model cannot be
#                                    auto-detected — set this to 1000000 there.

set -uo pipefail

input=$(cat)

[ "${DEV_TEAM_CONTEXT_CEILING:-on}" = "off" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0
echo "$input" | jq -e . >/dev/null 2>&1 || exit 0

tool_name=$(echo "$input" | jq -r '.tool_name // empty')
case "$tool_name" in
  Agent | Skill) ;;
  *) exit 0 ;;
esac

# Recovery skills are the way back under budget — never gate them.
if [ "$tool_name" = "Skill" ]; then
  skill=$(echo "$input" | jq -r '.tool_input.skill // .tool_input.name // empty')
  skill="${skill##*:}" # strip any "plugin:" prefix
  case "$skill" in
    context-summarization | context-loading-protocol | continue | review-summary | session-review)
      exit 0
      ;;
  esac
fi

transcript=$(echo "$input" | jq -r '.transcript_path // empty')
{ [ -z "$transcript" ] || [ ! -f "$transcript" ]; } && exit 0

# Occupancy = prompt-side tokens of the most recent assistant message that
# carries usage. tail keeps this cheap on a large transcript.
occ=$(tail -n 400 "$transcript" 2>/dev/null |
  jq -rc 'select(.message.usage != null)
          | ((.message.usage.input_tokens // 0)
             + (.message.usage.cache_read_input_tokens // 0)
             + (.message.usage.cache_creation_input_tokens // 0))' 2>/dev/null |
  tail -n 1)
{ [[ "$occ" =~ ^[0-9]+$ ]] && [ "$occ" -gt 0 ]; } || exit 0

# Resolve the context window: env override, else the 200000-token base window
# every current Claude model shares. We deliberately do not map model id →
# window: the transcript omits the [1m] suffix, so a 1M-context model is
# indistinguishable here — set DEV_TEAM_CONTEXT_WINDOW=1000000 in that case.
window="${DEV_TEAM_CONTEXT_WINDOW:-}"
{ [[ "$window" =~ ^[0-9]+$ ]] && [ "$window" -gt 0 ]; } || window=200000

ceiling="${DEV_TEAM_CONTEXT_CEILING_PCT:-40}"
{ [[ "$ceiling" =~ ^[0-9]+$ ]] && [ "$ceiling" -gt 0 ]; } || ceiling=40

pct=$((occ * 100 / window))
[ "$pct" -lt "$ceiling" ] && exit 0

label="loading agent '$(echo "$input" | jq -r '.tool_input.subagent_type // "?"')'"
[ "$tool_name" = "Skill" ] && label="invoking skill '$(echo "$input" | jq -r '.tool_input.skill // .tool_input.name // "?"')'"

msg="🪟 Context at ${pct}% of the ${window}-token window (≥ ${ceiling}% ceiling) before ${label}.
Per the Context Loading Protocol, summarize before loading more: run /context-summarization
(write a memory/ progress file, continue in a fresh context) and defer non-essential agents/skills.
Tune with DEV_TEAM_CONTEXT_WINDOW (set 1000000 on a 1M-context model) / DEV_TEAM_CONTEXT_CEILING_PCT;
DEV_TEAM_CONTEXT_STRICT=on hard-blocks; DEV_TEAM_CONTEXT_CEILING=off disables."

# Strict mode blocks every over-ceiling load. Warn mode nudges, but dedupes by
# 5-point bucket per session so a sustained over-budget run isn't spammed —
# a fresh nudge only when occupancy climbs into a higher bucket.
if [ "${DEV_TEAM_CONTEXT_STRICT:-off}" = "on" ]; then
  printf '%s\n' "$msg [blocked: DEV_TEAM_CONTEXT_STRICT=on]" >&2
  exit 2
fi

session=$(echo "$input" | jq -r '.session_id // "nosession"')
session=$(printf '%s' "$session" | tr -cd 'A-Za-z0-9_-')
[ -z "$session" ] && session="nosession"
marker="${TMPDIR:-/tmp}/dev-team-ctx-ceiling-${session}.last"
bucket=$((pct / 5))
last_bucket=0
[ -f "$marker" ] && last_bucket=$(cat "$marker" 2>/dev/null)
[[ "$last_bucket" =~ ^[0-9]+$ ]] || last_bucket=0
printf '%s' "$bucket" >"$marker" 2>/dev/null || true
[ "$bucket" -le "$last_bucket" ] && exit 0

printf '%s\n' "$msg" >&2
exit 0
