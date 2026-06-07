#!/usr/bin/env bats
# Tests for scripts/session_extract.py — the deterministic, zero-token
# session-log extractor (#127). Exercised against a committed fixture transcript
# that plants one signal of each class.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
EXTRACT="$REPO_ROOT/scripts/session_extract.py"
FIX="$REPO_ROOT/tests/fixtures/session-review/sample-transcript.jsonl"

_run() {
  python3 "$EXTRACT" --transcript "$FIX" --plugin-root "$REPO_ROOT/plugins/dev-team"
}

@test "extract: token signals (totals, cache-hit ratio, per-subagent)" {
  run _run
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.schema')" = "session-digest/v1" ]
  [ "$(echo "$output" | jq -r '.sessions')" = "1" ]
  [ "$(echo "$output" | jq -r '.token.totals.input_tokens')" = "4100" ]
  [ "$(echo "$output" | jq -r '.token.cache_hit_ratio')" = "0.8" ]
  [ "$(echo "$output" | jq -r '.token.by_subagent.sidechain')" = "1" ]
  [ "$(echo "$output" | jq -r '.token.by_skill."code-review".input_tokens')" = "1500" ]
}

@test "extract: rework signals (failed edit, repeated edits, retries, verify, denials, compaction)" {
  run _run
  [ "$(echo "$output" | jq -r '.rework.failed_edits')" = "1" ]
  [ "$(echo "$output" | jq -r '.rework.repeated_file_edits."a.ts"')" = "2" ]
  [ "$(echo "$output" | jq -r '.rework.retried_bash_commands')" = "1" ]
  [ "$(echo "$output" | jq -r '.rework.repeated_verify_runs')" = "2" ]
  [ "$(echo "$output" | jq -r '.rework.permission_denials')" = "1" ]
  [ "$(echo "$output" | jq -r '.rework.compaction_events')" = "1" ]
}

@test "extract: accuracy signals (errors by tool, error rate, corrections)" {
  run _run
  [ "$(echo "$output" | jq -r '.accuracy.tool_errors_by_tool.Edit')" = "1" ]
  [ "$(echo "$output" | jq -r '.accuracy.tool_errors_by_tool.Grep')" = "1" ]
  [ "$(echo "$output" | jq -r '.accuracy.tool_error_rate')" = "0.4" ]
  [ "$(echo "$output" | jq -r '.accuracy.user_correction_turns')" = "1" ]
}

@test "extract: utilization (invoked + never-observed registry items)" {
  run _run
  [ "$(echo "$output" | jq -r '.utilization.skills_invoked."code-review"')" = "2" ]
  # the plugin ships many skills; nearly all are never-observed in this fixture
  [ "$(echo "$output" | jq -r '.utilization.never_observed_skills | length > 10')" = "true" ]
  # code-review WAS observed, so it must not be in never-observed
  run bash -c "python3 '$EXTRACT' --transcript '$FIX' --plugin-root '$REPO_ROOT/plugins/dev-team' | jq -r '.utilization.never_observed_skills | index(\"code-review\")'"
  [ "$output" = "null" ]
}

@test "extract: deterministic — identical bytes on repeated runs" {
  a="$(_run)"; b="$(_run)"
  [ "$a" = "$b" ]
}

@test "extract: privacy — no raw prompt/code/command content in the digest" {
  run _run
  # planted raw strings that must NEVER appear in a metrics-only digest
  [[ "$output" != *"old_string not found"* ]]
  [[ "$output" != *"npm test"* ]]
  [[ "$output" != *"revert that change"* ]]
  [[ "$output" != *"/proj/src"* ]]            # absolute paths reduced to basenames
}

@test "extract: empty input yields a well-formed empty digest" {
  empty="$(mktemp)"
  run python3 "$EXTRACT" --transcript "$empty" --plugin-root "$REPO_ROOT/plugins/dev-team"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.token.totals.input_tokens // 0')" = "0" ]
  rm -f "$empty"
}
