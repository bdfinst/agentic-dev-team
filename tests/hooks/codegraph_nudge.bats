#!/usr/bin/env bats
# Tests for hooks/codegraph-nudge.sh — PreToolUse nudge that recommends
# codegraph_* MCP tools over multi-file Read/Grep/Glob exploration when
# a CodeGraph index (.codegraph/) is present in the project.

HOOK="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/codegraph-nudge.sh"
MARK_HOOK="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/codegraph-turn-mark.sh"

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
}

# ---------------------------------------------------------------------------
# Step 1 — silent when .codegraph/ is absent in cwd
# ---------------------------------------------------------------------------

@test "silent_when_codegraph_absent: exit 0 with no output for any tool" {
  local input
  input=$(printf '%s' "{\"tool_name\":\"Read\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"tool_input\":{\"file_path\":\"$BATS_TMPDIR_CASE/foo.txt\"}}")

  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Step 2 — Read tool-name is always single-file → silent
# ---------------------------------------------------------------------------

@test "silent_on_read_when_codegraph_present: exit 0 with no output" {
  mkdir -p "$BATS_TMPDIR_CASE/.codegraph"
  echo "hello" > "$BATS_TMPDIR_CASE/foo.txt"
  local input
  input=$(printf '%s' "{\"tool_name\":\"Read\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"tool_input\":{\"file_path\":\"$BATS_TMPDIR_CASE/foo.txt\"}}")

  run bash -c "echo '$input' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Step 3 — Grep/Glob argument-shape heuristic → warn on multi-file shape
# ---------------------------------------------------------------------------

# The expected warning constant — kept in sync with WARN_MSG in
# codegraph-nudge.sh. Updating this string requires updating the hook.
EXPECTED_WARN_MSG='[codegraph-nudge] CodeGraph is initialized in this project. Prefer codegraph_context or codegraph_explore for multi-file exploration; Grep/Glob/Read for confirming a specific detail.'

@test "warns_on_grep_with_directory_path: stderr equals WARN_MSG verbatim, exit 0" {
  mkdir -p "$BATS_TMPDIR_CASE/.codegraph" "$BATS_TMPDIR_CASE/src"
  echo "one" > "$BATS_TMPDIR_CASE/src/a.ts"
  local input
  input=$(printf '%s' "{\"tool_name\":\"Grep\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"tool_input\":{\"pattern\":\"foo\",\"path\":\"$BATS_TMPDIR_CASE/src\"}}")

  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ "$output" = "$EXPECTED_WARN_MSG" ]
}

@test "silent_on_grep_with_file_path: no warning when path is a regular file" {
  mkdir -p "$BATS_TMPDIR_CASE/.codegraph"
  echo "one" > "$BATS_TMPDIR_CASE/foo.txt"
  local input
  input=$(printf '%s' "{\"tool_name\":\"Grep\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"tool_input\":{\"pattern\":\"foo\",\"path\":\"$BATS_TMPDIR_CASE/foo.txt\"}}")

  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "warns_on_glob_with_wildcard_pattern: stderr equals WARN_MSG verbatim, exit 0" {
  mkdir -p "$BATS_TMPDIR_CASE/.codegraph"
  local input
  input=$(printf '%s' "{\"tool_name\":\"Glob\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"tool_input\":{\"pattern\":\"**/*.ts\"}}")

  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ "$output" = "$EXPECTED_WARN_MSG" ]
}

@test "silent_on_glob_with_literal_pattern: no warning when pattern has no metachars" {
  mkdir -p "$BATS_TMPDIR_CASE/.codegraph"
  local input
  input=$(printf '%s' "{\"tool_name\":\"Glob\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"tool_input\":{\"pattern\":\"package.json\"}}")

  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Step 4 — sentinel-based turn detection
#
# A PostToolUse hook (codegraph-turn-mark.sh) writes the sentinel when
# any mcp__codegraph__* tool completes. The nudge hook reads the sentinel
# and suppresses the warning when:
#   (a) sentinel.transcript_id matches the current transcript, AND
#   (b) sentinel.turn_counter matches the count of `"type":"user"`
#       markers in the current transcript tail.
# Both are derived the same way on both sides so they agree.
# ---------------------------------------------------------------------------

# Build a minimal Claude Code transcript JSONL with N user-message markers.
# Each "user" line bumps the turn counter that the hook uses.
_write_transcript() {
  local path="$1"; shift
  local user_count="$1"; shift
  local extra="${1:-}"
  : > "$path"
  for ((i=0; i<user_count; i++)); do
    printf '{"type":"user","message":"u%d"}\n' "$i" >> "$path"
  done
  if [ -n "$extra" ]; then
    printf '%s\n' "$extra" >> "$path"
  fi
}

# Build the project tree (cwd with .codegraph/ and .claude/) and return
# the path via $1 (out var) so tests stay declarative.
_setup_codegraph_project() {
  mkdir -p "$BATS_TMPDIR_CASE/.codegraph"
  mkdir -p "$BATS_TMPDIR_CASE/.claude"
  mkdir -p "$BATS_TMPDIR_CASE/transcripts"
  mkdir -p "$BATS_TMPDIR_CASE/src"
  echo "one" > "$BATS_TMPDIR_CASE/src/a.ts"
}

@test "silent_after_codegraph_used_this_turn_for_grep: sentinel matches current turn" {
  _setup_codegraph_project
  local tx="$BATS_TMPDIR_CASE/transcripts/abc123.jsonl"
  _write_transcript "$tx" 3
  printf '{"transcript_id":"abc123","turn_counter":3}\n' \
    > "$BATS_TMPDIR_CASE/.claude/codegraph-turn-state.json"

  local input
  input=$(printf '%s' "{\"tool_name\":\"Grep\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"transcript_path\":\"$tx\",\"tool_input\":{\"pattern\":\"foo\",\"path\":\"$BATS_TMPDIR_CASE/src\"}}")

  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "silent_after_codegraph_used_this_turn_for_glob: sentinel suppresses Glob branch too" {
  _setup_codegraph_project
  local tx="$BATS_TMPDIR_CASE/transcripts/abc123.jsonl"
  _write_transcript "$tx" 2
  printf '{"transcript_id":"abc123","turn_counter":2}\n' \
    > "$BATS_TMPDIR_CASE/.claude/codegraph-turn-state.json"

  local input
  input=$(printf '%s' "{\"tool_name\":\"Glob\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"transcript_path\":\"$tx\",\"tool_input\":{\"pattern\":\"**/*.ts\"}}")

  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "warns_when_sentinel_is_for_prior_turn: turn boundary reset" {
  _setup_codegraph_project
  local tx="$BATS_TMPDIR_CASE/transcripts/abc123.jsonl"
  _write_transcript "$tx" 4
  # Sentinel from a previous turn (counter=3 < current=4)
  printf '{"transcript_id":"abc123","turn_counter":3}\n' \
    > "$BATS_TMPDIR_CASE/.claude/codegraph-turn-state.json"

  local input
  input=$(printf '%s' "{\"tool_name\":\"Grep\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"transcript_path\":\"$tx\",\"tool_input\":{\"pattern\":\"foo\",\"path\":\"$BATS_TMPDIR_CASE/src\"}}")

  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ "$output" = "$EXPECTED_WARN_MSG" ]
}

@test "warns_when_sentinel_is_for_different_transcript" {
  _setup_codegraph_project
  local tx="$BATS_TMPDIR_CASE/transcripts/abc123.jsonl"
  _write_transcript "$tx" 2
  # Sentinel from a different transcript id
  printf '{"transcript_id":"other","turn_counter":2}\n' \
    > "$BATS_TMPDIR_CASE/.claude/codegraph-turn-state.json"

  local input
  input=$(printf '%s' "{\"tool_name\":\"Grep\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"transcript_path\":\"$tx\",\"tool_input\":{\"pattern\":\"foo\",\"path\":\"$BATS_TMPDIR_CASE/src\"}}")

  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ "$output" = "$EXPECTED_WARN_MSG" ]
}

@test "warns_when_sentinel_missing" {
  _setup_codegraph_project
  local tx="$BATS_TMPDIR_CASE/transcripts/abc123.jsonl"
  _write_transcript "$tx" 1
  # No sentinel file written.

  local input
  input=$(printf '%s' "{\"tool_name\":\"Grep\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"transcript_path\":\"$tx\",\"tool_input\":{\"pattern\":\"foo\",\"path\":\"$BATS_TMPDIR_CASE/src\"}}")

  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ "$output" = "$EXPECTED_WARN_MSG" ]
}

@test "turn_mark_hook_writes_sentinel: PostToolUse for mcp__codegraph__* creates sentinel" {
  _setup_codegraph_project
  local tx="$BATS_TMPDIR_CASE/transcripts/abc123.jsonl"
  _write_transcript "$tx" 2
  local input
  input=$(printf '%s' "{\"tool_name\":\"mcp__codegraph__codegraph_context\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"transcript_path\":\"$tx\"}")

  run bash -c "echo '$input' | CLAUDE_PROJECT_DIR='$BATS_TMPDIR_CASE' bash '$MARK_HOOK'"
  [ "$status" -eq 0 ]

  local sentinel="$BATS_TMPDIR_CASE/.claude/codegraph-turn-state.json"
  [ -f "$sentinel" ]

  local tid
  tid=$(jq -r '.transcript_id' "$sentinel")
  local tc
  tc=$(jq -r '.turn_counter' "$sentinel")
  [ "$tid" = "abc123" ]
  [ "$tc" = "2" ]
}

@test "turn_mark_hook_ignores_non_codegraph_tools" {
  _setup_codegraph_project
  local tx="$BATS_TMPDIR_CASE/transcripts/abc123.jsonl"
  _write_transcript "$tx" 1
  local input
  input=$(printf '%s' "{\"tool_name\":\"Bash\",\"cwd\":\"$BATS_TMPDIR_CASE\",\"transcript_path\":\"$tx\"}")

  run bash -c "echo '$input' | CLAUDE_PROJECT_DIR='$BATS_TMPDIR_CASE' bash '$MARK_HOOK'"
  [ "$status" -eq 0 ]
  [ ! -f "$BATS_TMPDIR_CASE/.claude/codegraph-turn-state.json" ]
}
