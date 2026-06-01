#!/usr/bin/env bats
# Tests for hooks/codegraph-nudge.sh — PreToolUse nudge that recommends
# codegraph_* MCP tools over multi-file Read/Grep/Glob exploration when
# a CodeGraph index (.codegraph/) is present in the project.

HOOK="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/codegraph-nudge.sh"

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
