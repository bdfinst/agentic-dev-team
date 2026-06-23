#!/usr/bin/env bats
# Tests for per-artifact telemetry: _upsert_artifact_usage in telemetry.sh.
# Slice 2: cold-start, repeat invocation, invalid skill, disabled consent,
# file-based opt-out, malformed file recovery, unwritable directory.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
HOOK="$REPO_ROOT/plugins/dev-team/hooks/telemetry.sh"
LIFECYCLE_DOC="$REPO_ROOT/plugins/dev-team/knowledge/artifact-lifecycle.md"

setup() {
  D="$(mktemp -d)"
  mkdir -p "$D/.claude"
}
teardown() { rm -rf "$D"; }

_enable_env() { export DEV_TEAM_TELEMETRY=on; }
_disable_env() { unset DEV_TEAM_TELEMETRY 2>/dev/null || true; }
_enable_file() { echo '{"enabled":true}' > "$D/.claude/telemetry.json"; }
_disable_file() { echo '{"enabled":false}' > "$D/.claude/telemetry.json"; }

_skill_event() {
  echo "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Skill\",\"tool_input\":{\"skill\":\"${1}\"},\"cwd\":\"$D\"}"
}

_send() { echo "$1" | bash "$HOOK"; }

# ---------------------------------------------------------------------------
# Knowledge file
# ---------------------------------------------------------------------------

@test "knowledge: artifact-lifecycle.md exists" {
  [ -f "$LIFECYCLE_DOC" ]
}

@test "knowledge: defines three lifecycle states: active, stale, archived" {
  grep -q "active" "$LIFECYCLE_DOC"
  grep -q "stale" "$LIFECYCLE_DOC"
  grep -q "archived" "$LIFECYCLE_DOC"
}

@test "knowledge: stale threshold is 30 days" {
  grep -q "30" "$LIFECYCLE_DOC"
}

@test "knowledge: archived threshold is 90 days" {
  grep -q "90" "$LIFECYCLE_DOC"
}

@test "knowledge: documents pinned exemption" {
  grep -qi "pinned" "$LIFECYCLE_DOC"
}

# ---------------------------------------------------------------------------
# Cold-start: creates directory and file with correct entry
# ---------------------------------------------------------------------------

@test "artifact-usage: cold-start creates artifact-usage.json with use_count=1" {
  _enable_env
  _send "$(_skill_event "session-review")"
  [ -f "$D/metrics/artifact-usage.json" ]
  run jq -r '.["session-review"].use_count' "$D/metrics/artifact-usage.json"
  [ "$output" = "1" ]
}

@test "artifact-usage: cold-start sets lifecycle to active" {
  _enable_env
  _send "$(_skill_event "session-review")"
  run jq -r '.["session-review"].lifecycle' "$D/metrics/artifact-usage.json"
  [ "$output" = "active" ]
}

@test "artifact-usage: cold-start sets last_used_at to an ISO-8601 UTC timestamp" {
  _enable_env
  _send "$(_skill_event "session-review")"
  run jq -r '.["session-review"].last_used_at' "$D/metrics/artifact-usage.json"
  [[ "$output" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
}

@test "artifact-usage: cold-start creates metrics/ directory when absent" {
  _enable_env
  [ ! -d "$D/metrics" ]
  _send "$(_skill_event "code-review")"
  [ -d "$D/metrics" ]
}

# ---------------------------------------------------------------------------
# Repeat invocation: increments use_count, preserves lifecycle
# ---------------------------------------------------------------------------

@test "artifact-usage: repeat invocation increments use_count" {
  _enable_env
  _send "$(_skill_event "session-review")"
  _send "$(_skill_event "session-review")"
  _send "$(_skill_event "session-review")"
  run jq -r '.["session-review"].use_count' "$D/metrics/artifact-usage.json"
  [ "$output" = "3" ]
}

@test "artifact-usage: repeat invocation preserves existing lifecycle value" {
  _enable_env
  # Pre-seed with lifecycle=stale
  mkdir -p "$D/metrics"
  echo '{"session-review":{"use_count":3,"last_used_at":"2026-01-01T00:00:00Z","lifecycle":"stale"}}' \
    > "$D/metrics/artifact-usage.json"
  _send "$(_skill_event "session-review")"
  run jq -r '.["session-review"].lifecycle' "$D/metrics/artifact-usage.json"
  [ "$output" = "stale" ]
}

@test "artifact-usage: repeat invocation increments from existing use_count" {
  _enable_env
  mkdir -p "$D/metrics"
  echo '{"session-review":{"use_count":3,"last_used_at":"2026-01-01T00:00:00Z","lifecycle":"stale"}}' \
    > "$D/metrics/artifact-usage.json"
  _send "$(_skill_event "session-review")"
  run jq -r '.["session-review"].use_count' "$D/metrics/artifact-usage.json"
  [ "$output" = "4" ]
}

# ---------------------------------------------------------------------------
# Invalid skill name: not recorded
# ---------------------------------------------------------------------------

@test "artifact-usage: empty skill name produces no artifact-usage.json" {
  _enable_env
  _send "$(_skill_event "")"
  [ ! -f "$D/metrics/artifact-usage.json" ]
}

@test "artifact-usage: empty skill name hook exits 0" {
  _enable_env
  run bash -c "echo '$(_skill_event "")' | bash '$HOOK'"
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Consent: disabled telemetry writes nothing
# ---------------------------------------------------------------------------

@test "artifact-usage: not written when telemetry is disabled (no env, no file)" {
  _disable_env
  _send "$(_skill_event "session-review")"
  [ ! -f "$D/metrics/artifact-usage.json" ]
}

# ---------------------------------------------------------------------------
# File-based opt-out overrides env-var opt-in
# ---------------------------------------------------------------------------

@test "artifact-usage: file-based opt-out overrides DEV_TEAM_TELEMETRY=on" {
  _enable_env
  _disable_file
  _send "$(_skill_event "session-review")"
  [ ! -f "$D/metrics/artifact-usage.json" ]
}

# ---------------------------------------------------------------------------
# Malformed JSON recovery
# ---------------------------------------------------------------------------

@test "artifact-usage: malformed artifact-usage.json is discarded and rewritten" {
  _enable_env
  mkdir -p "$D/metrics"
  echo "{{broken" > "$D/metrics/artifact-usage.json"
  run bash -c "echo '$(_skill_event "session-review")' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  run jq -e . "$D/metrics/artifact-usage.json"
  [ "$status" -eq 0 ]
  run jq -r '.["session-review"].use_count' "$D/metrics/artifact-usage.json"
  [ "$output" = "1" ]
}

@test "artifact-usage: malformed artifact-usage.json emits a WARN to stderr" {
  _enable_env
  mkdir -p "$D/metrics"
  echo "{{broken" > "$D/metrics/artifact-usage.json"
  run bash -c "echo '$(_skill_event "session-review")' | bash '$HOOK' 2>&1"
  [[ "$output" == *"WARN"* ]]
}

# ---------------------------------------------------------------------------
# Unwritable directory: graceful exit 0
# ---------------------------------------------------------------------------

@test "artifact-usage: unwritable metrics/ directory causes graceful exit 0" {
  [[ "$(id -u)" -ne 0 ]] || skip "root bypasses directory permissions"
  _enable_env
  mkdir -p "$D/metrics"
  chmod 000 "$D/metrics"
  run bash -c "echo '$(_skill_event "session-review")' | bash '$HOOK'"
  chmod 755 "$D/metrics"  # restore for teardown
  [ "$status" -eq 0 ]
}

@test "artifact-usage: unwritable metrics/ directory produces no artifact-usage.json" {
  [[ "$(id -u)" -ne 0 ]] || skip "root bypasses directory permissions"
  _enable_env
  mkdir -p "$D/metrics"
  chmod 000 "$D/metrics"
  run bash -c "echo '$(_skill_event "session-review")' | bash '$HOOK'"
  chmod 755 "$D/metrics"
  [ ! -f "$D/metrics/artifact-usage.json" ]
}

# ---------------------------------------------------------------------------
# Multiple entries coexist
# ---------------------------------------------------------------------------

@test "artifact-usage: two different skills produce two entries" {
  _enable_env
  _send "$(_skill_event "session-review")"
  _send "$(_skill_event "feedback-learning")"
  run jq -r 'keys | length' "$D/metrics/artifact-usage.json"
  [ "$output" = "2" ]
}
