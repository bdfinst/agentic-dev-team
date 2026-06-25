#!/usr/bin/env bats
# Tests for hooks/context-ceiling-guard.sh — PreToolUse hook (Agent + Skill)
# that enforces the 40% context-window ceiling. Warns by default, blocks under
# DEV_TEAM_CONTEXT_STRICT=on, never gates recovery skills, and fails open.

HOOK="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/context-ceiling-guard.sh"

setup() {
  CASE="$(mktemp -d)"
  TR="$CASE/transcript.jsonl"
  # Isolate the per-session dedupe marker inside the case dir.
  export TMPDIR="$CASE"
  # Neutralize any inherited config so tests control the knobs.
  unset DEV_TEAM_CONTEXT_CEILING DEV_TEAM_CONTEXT_STRICT \
    DEV_TEAM_CONTEXT_CEILING_PCT DEV_TEAM_CONTEXT_WINDOW
}

teardown() { rm -rf "$CASE"; }

# Write a transcript whose latest usage line totals $1 prompt-side tokens.
write_transcript() {
  printf '%s\n' \
    "{\"message\":{\"model\":\"claude-opus-4-8\",\"usage\":{\"input_tokens\":2,\"cache_read_input_tokens\":$(($1 - 2)),\"cache_creation_input_tokens\":0}}}" \
    >"$TR"
}

# Build a hook stdin payload: $1=tool_name, $2=tool_input JSON object.
mkinput() {
  printf '{"tool_name":"%s","session_id":"s1","transcript_path":"%s","tool_input":%s}' \
    "$1" "$TR" "$2"
}

@test "silent below the ceiling" {
  write_transcript 50000 # 50000/200000 = 25%
  run bash -c "echo '$(mkinput Agent '{"subagent_type":"x"}')' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "warns (exit 0) on Agent load over the ceiling" {
  write_transcript 100000 # 50%
  run bash -c "echo '$(mkinput Agent '{"subagent_type":"dev-team:doc-review"}')' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [[ "$output" == *"50%"* ]]
  [[ "$output" == *"context-summarization"* ]]
}

@test "blocks (exit 2) over the ceiling under strict mode" {
  write_transcript 100000
  export DEV_TEAM_CONTEXT_STRICT=on
  run bash -c "echo '$(mkinput Skill '{"skill":"plan"}')' | bash '$HOOK'"
  [ "$status" -eq 2 ]
  [[ "$output" == *"blocked"* ]]
}

@test "never gates a recovery skill, even strict + over ceiling" {
  write_transcript 180000 # 90%
  export DEV_TEAM_CONTEXT_STRICT=on
  run bash -c "echo '$(mkinput Skill '{"skill":"dev-team:context-summarization"}')' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "ignores tools other than Agent/Skill" {
  write_transcript 180000
  run bash -c "echo '$(mkinput Read '{"file_path":"/x"}')' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "disabled via DEV_TEAM_CONTEXT_CEILING=off" {
  write_transcript 180000
  export DEV_TEAM_CONTEXT_CEILING=off
  run bash -c "echo '$(mkinput Agent '{"subagent_type":"x"}')' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "DEV_TEAM_CONTEXT_WINDOW override changes the verdict" {
  write_transcript 100000 # 100000/1000000 = 10% with a 1M window
  export DEV_TEAM_CONTEXT_WINDOW=1000000
  run bash -c "echo '$(mkinput Agent '{"subagent_type":"x"}')' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "DEV_TEAM_CONTEXT_CEILING_PCT lowers the trigger point" {
  write_transcript 60000 # 30%
  export DEV_TEAM_CONTEXT_CEILING_PCT=25
  run bash -c "echo '$(mkinput Agent '{"subagent_type":"x"}')' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [[ "$output" == *"30%"* ]]
}

@test "fail-open when the transcript is missing" {
  run bash -c "printf '{\"tool_name\":\"Agent\",\"transcript_path\":\"$CASE/nope.jsonl\",\"tool_input\":{}}' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "fail-open on malformed JSON" {
  run bash -c "printf 'not json' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "warn dedupes within a 5-point bucket, re-warns on a higher bucket" {
  write_transcript 100000 # 50% → bucket 10
  run bash -c "echo '$(mkinput Agent '{"subagent_type":"x"}')' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [[ "$output" == *"50%"* ]]

  # Same bucket → suppressed (still allowed).
  run bash -c "echo '$(mkinput Agent '{"subagent_type":"x"}')' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]

  # Climb into a higher bucket → fresh warning.
  write_transcript 140000 # 70% → bucket 14
  run bash -c "echo '$(mkinput Agent '{"subagent_type":"x"}')' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [[ "$output" == *"70%"* ]]
}
