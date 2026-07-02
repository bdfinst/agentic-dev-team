#!/usr/bin/env bats
# Verify key hooks are registered at the right lifecycle points in settings.json.

SETTINGS="$BATS_TEST_DIRNAME/../../plugins/dev-team/settings.json"

@test "settings.json is valid JSON" {
  run jq . "$SETTINGS"
  [ "$status" -eq 0 ]
}

@test "mutation_gate.py is registered in PostToolUse Bash hooks" {
  run jq -e '
    .hooks.PostToolUse[]
    | select(.matcher == "Bash")
    | .hooks[]
    | select(.command | contains("mutation_gate.py"))
  ' "$SETTINGS"
  [ "$status" -eq 0 ]
}

@test "mutation_gate is in PostToolUse (not PreToolUse)" {
  # Must NOT appear in PreToolUse
  run jq -e '
    .hooks.PreToolUse[]
    | .hooks[]
    | select(.command | contains("mutation_gate.py"))
  ' "$SETTINGS"
  # Should find nothing — status 1 means not found, which is what we want
  [ "$status" -ne 0 ]
}

@test "session_learning_trigger.py is registered in SessionStop hooks" {
  run jq -e '
    .hooks.SessionStop[]
    | .hooks[]
    | select(.command | contains("session_learning_trigger.py"))
  ' "$SETTINGS"
  [ "$status" -eq 0 ]
}
