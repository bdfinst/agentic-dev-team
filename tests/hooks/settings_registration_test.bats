#!/usr/bin/env bats
# Step 8: Verify mutation-gate is registered in settings.json

SETTINGS="$BATS_TEST_DIRNAME/../../plugins/dev-team/settings.json"

@test "settings.json is valid JSON" {
  run jq . "$SETTINGS"
  [ "$status" -eq 0 ]
}

@test "mutation-gate.sh is registered in PostToolUse Bash hooks" {
  run jq -e '
    .hooks.PostToolUse[]
    | select(.matcher == "Bash")
    | .hooks[]
    | select(.command | contains("mutation-gate.sh"))
  ' "$SETTINGS"
  [ "$status" -eq 0 ]
}

@test "mutation-gate is in PostToolUse (not PreToolUse)" {
  # Must NOT appear in PreToolUse
  run jq -e '
    .hooks.PreToolUse[]
    | .hooks[]
    | select(.command | contains("mutation-gate.sh"))
  ' "$SETTINGS"
  # Should find nothing — status 1 means not found, which is what we want
  [ "$status" -ne 0 ]
}

@test "session-learning-trigger.sh is registered in SessionStop hooks" {
  run jq -e '
    .hooks.SessionStop[]
    | .hooks[]
    | select(.command | contains("session-learning-trigger.sh"))
  ' "$SETTINGS"
  [ "$status" -eq 0 ]
}
