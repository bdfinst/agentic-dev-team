#!/usr/bin/env bats
# Tests for hooks/overrides-banner.sh — SessionStart hook that surfaces
# the one-line note when .claude/model-overrides.json exists.
# AC19, Scenario "Active overrides surface a one-line session note".

HOOK="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/overrides-banner.sh"
SETTINGS_JSON="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/settings.json"

EXPECTED_BANNER='Note: model routing overrides active — run /model-routing-check to review.'

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  mkdir -p "$BATS_TMPDIR_CASE/.claude"
  export MODEL_OVERRIDES_JSON="$BATS_TMPDIR_CASE/.claude/model-overrides.json"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset MODEL_OVERRIDES_JSON
}

# Helper: build a SessionStart-shaped stdin payload. Claude Code's
# SessionStart contract includes cwd and transcript_path; we don't need
# either, but providing them mirrors real input.
_session_start_input() {
  jq -nc --arg cwd "$BATS_TMPDIR_CASE" \
    '{hook_event_name: "SessionStart", cwd: $cwd}'
}

@test "banner: prints literal line to stderr when overrides file exists" {
  cat > "$MODEL_OVERRIDES_JSON" <<'EOF'
{ "tier_aliases": { "haiku": "sonnet" } }
EOF
  local input
  input=$(_session_start_input)
  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ "$output" = "$EXPECTED_BANNER" ]
}

@test "banner: prints nothing when overrides file does not exist" {
  [ ! -e "$MODEL_OVERRIDES_JSON" ]
  local input
  input=$(_session_start_input)
  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "banner: malformed stdin fails open (silent, exit 0)" {
  run bash -c "echo 'not json' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "banner: registered in settings.json under SessionStart" {
  [ -f "$SETTINGS_JSON" ]
  run jq -e '.hooks.SessionStart[] | .hooks[] | select(.command | contains("overrides-banner.sh"))' "$SETTINGS_JSON"
  [ "$status" -eq 0 ]
}
