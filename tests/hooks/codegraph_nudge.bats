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
