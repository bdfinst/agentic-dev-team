#!/usr/bin/env bats
# Verify the codegraph-nudge and codegraph-turn-mark hooks are registered
# in plugins/agentic-dev-team/settings.json. Per Plan Step 7, the nudge
# hook is registered as three separate per-tool PreToolUse entries (Read,
# Grep, Glob) rather than a pipe-delimited regex matcher — there is no
# existing precedent for `Read|Grep|Glob` in this file and per-tool entries
# are unambiguous. The mark hook is registered once on the regex matcher
# `mcp__codegraph__.*`.

SETTINGS="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/settings.json"

@test "settings.json is valid JSON (codegraph-nudge changes)" {
  run jq . "$SETTINGS"
  [ "$status" -eq 0 ]
}

@test "codegraph-nudge.sh is registered in PreToolUse Read" {
  run jq -e '
    .hooks.PreToolUse[]
    | select(.matcher == "Read")
    | .hooks[]
    | select(.command | contains("codegraph-nudge.sh"))
  ' "$SETTINGS"
  [ "$status" -eq 0 ]
}

@test "codegraph-nudge.sh is registered in PreToolUse Grep" {
  run jq -e '
    .hooks.PreToolUse[]
    | select(.matcher == "Grep")
    | .hooks[]
    | select(.command | contains("codegraph-nudge.sh"))
  ' "$SETTINGS"
  [ "$status" -eq 0 ]
}

@test "codegraph-nudge.sh is registered in PreToolUse Glob" {
  run jq -e '
    .hooks.PreToolUse[]
    | select(.matcher == "Glob")
    | .hooks[]
    | select(.command | contains("codegraph-nudge.sh"))
  ' "$SETTINGS"
  [ "$status" -eq 0 ]
}

@test "codegraph-turn-mark.sh is registered in PostToolUse mcp__codegraph__.*" {
  run jq -e '
    .hooks.PostToolUse[]
    | select(.matcher == "mcp__codegraph__.*")
    | .hooks[]
    | select(.command | contains("codegraph-turn-mark.sh"))
  ' "$SETTINGS"
  [ "$status" -eq 0 ]
}

@test "codegraph-nudge.sh does NOT appear under a regex matcher Read|Grep|Glob" {
  # Per the plan, we chose per-tool entries over a pipe-delimited regex.
  # Catch a future regression that introduces the regex form.
  run jq -e '
    .hooks.PreToolUse[]
    | select(.matcher | test("Read\\|.*Grep|Read\\|.*Glob|Grep\\|.*Glob"))
    | .hooks[]
    | select(.command | contains("codegraph-nudge.sh"))
  ' "$SETTINGS"
  [ "$status" -ne 0 ]
}
