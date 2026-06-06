#!/usr/bin/env bats
# Tests for the opt-in telemetry beacon (issue #106): default-off consent,
# command/skill capture, gate fired/bypassed capture, privacy (no payloads),
# and the report aggregation.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
HOOK="$REPO_ROOT/plugins/dev-team/hooks/telemetry.sh"
REPORT="$REPO_ROOT/plugins/dev-team/hooks/lib/telemetry_report.py"

setup() { D="$(mktemp -d)"; }
teardown() { rm -rf "$D"; }

_enable() { mkdir -p "$D/.claude"; echo '{"enabled":true}' > "$D/.claude/telemetry.json"; }
_send() { echo "$1" | bash "$HOOK"; }

@test "telemetry: OFF by default — nothing is recorded" {
  _send "{\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"/specs\",\"cwd\":\"$D\"}"
  [ ! -f "$D/metrics/telemetry.jsonl" ]
}

@test "telemetry: enabling via .claude/telemetry.json records a command event" {
  _enable
  _send "{\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"/code-review --scope x\",\"cwd\":\"$D\"}"
  [ -f "$D/metrics/telemetry.jsonl" ]
  run jq -r '.event + " " + .name' "$D/metrics/telemetry.jsonl"
  [ "$output" = "command code-review" ]
}

@test "telemetry: env DEV_TEAM_TELEMETRY=on also enables" {
  run bash -c "DEV_TEAM_TELEMETRY=on; export DEV_TEAM_TELEMETRY; echo '{\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"/build\",\"cwd\":\"$D\"}' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ "$(jq -r '.name' "$D/metrics/telemetry.jsonl")" = "build" ]
}

@test "telemetry: records gate fired vs bypassed for git commit" {
  _enable
  _send "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git commit -m hello\"},\"cwd\":\"$D\"}"
  _send "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git commit --no-verify -m skip\"},\"cwd\":\"$D\"}"
  run jq -rs '[.[].outcome] | join(",")' "$D/metrics/telemetry.jsonl"
  [ "$output" = "fired,bypassed" ]
}

@test "telemetry: privacy — no prompt text, command string, or paths in the log" {
  _enable
  _send "{\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"/specs SECRET_PROMPT_TEXT /home/u/secret\",\"cwd\":\"$D\"}"
  _send "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git commit -m SECRET_MESSAGE\"},\"cwd\":\"$D\"}"
  run cat "$D/metrics/telemetry.jsonl"
  [[ "$output" != *"SECRET_PROMPT_TEXT"* ]]
  [[ "$output" != *"SECRET_MESSAGE"* ]]
  [[ "$output" != *"/home/u/secret"* ]]
  # Only the documented keys are present.
  run jq -rs 'all(.[]; (keys | sort) == ["event","name","outcome","plugin_version","ts"])' "$D/metrics/telemetry.jsonl"
  [ "$output" = "true" ]
}

@test "telemetry: non-Bash PreToolUse and non-slash prompts record nothing" {
  _enable
  _send "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Read\",\"tool_input\":{\"file_path\":\"x\"},\"cwd\":\"$D\"}"
  _send "{\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"just a normal question\",\"cwd\":\"$D\"}"
  [ ! -f "$D/metrics/telemetry.jsonl" ]
}

@test "report: aggregates usage and bypass rate" {
  cat > "$D/t.jsonl" <<'EOF'
{"event":"command","name":"specs","outcome":"invoked","plugin_version":"1"}
{"event":"command","name":"specs","outcome":"invoked","plugin_version":"1"}
{"event":"command","name":"build","outcome":"invoked","plugin_version":"1"}
{"event":"gate","name":"pre-commit-review","outcome":"fired","plugin_version":"1"}
{"event":"gate","name":"pre-commit-review","outcome":"bypassed","plugin_version":"1"}
{"event":"gate","name":"pre-commit-review","outcome":"bypassed","plugin_version":"1"}
EOF
  run python3 "$REPORT" --log "$D/t.jsonl" --json
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.command_usage.specs')" = "2" ]
  [ "$(echo "$output" | jq -r '.gates."pre-commit-review".bypass_rate')" = "0.6667" ]
}

@test "report: disabled (no log) says nothing left the machine" {
  run python3 "$REPORT" --log "$D/none.jsonl"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Nothing has left the machine"* ]]
}

@test "settings.json registers telemetry.sh on UserPromptSubmit and PreToolUse Bash" {
  run jq -e '.hooks.UserPromptSubmit[].hooks[] | select(.command | contains("telemetry.sh"))' \
    "$REPO_ROOT/plugins/dev-team/settings.json"
  [ "$status" -eq 0 ]
  run jq -e '.hooks.PreToolUse[] | select(.matcher=="Bash") | .hooks[] | select(.command | contains("telemetry.sh"))' \
    "$REPO_ROOT/plugins/dev-team/settings.json"
  [ "$status" -eq 0 ]
}
