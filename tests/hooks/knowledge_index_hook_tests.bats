#!/usr/bin/env bats
# Tests for hooks/knowledge-index.sh — PostToolUse hook on Edit|Write.
# AC10 (rebuild on corpus edit), AC11 (skip unrelated), AC12 (fail-open),
# AC22 (PostToolUse settings registration).

HOOK="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/knowledge-index.sh"
SETTINGS_JSON="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/settings.json"
FAKE_BIN="$BATS_TEST_DIRNAME/fake-bin"
SENTINEL=""

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  SENTINEL="$BATS_TMPDIR_CASE/builder-invoked.sentinel"
  rm -f "$SENTINEL"
  # Install a deterministic builder shim. The hook resolves the builder
  # via BASH_SOURCE, so we shim by overriding the BUILDER env var the
  # hook honors as a TEST-ONLY seam.
  cat > "$BATS_TMPDIR_CASE/fake-builder.sh" <<EOF
#!/usr/bin/env bash
touch "$SENTINEL"
if [[ "\${FAKE_BUILDER_MODE:-ok}" = "fail" ]]; then
  echo "boom" >&2
  exit 1
fi
exit 0
EOF
  chmod +x "$BATS_TMPDIR_CASE/fake-builder.sh"
  export KNOWLEDGE_INDEX_BUILDER="$BATS_TMPDIR_CASE/fake-builder.sh"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset KNOWLEDGE_INDEX_BUILDER FAKE_BUILDER_MODE
}

_hook_input() {
  # Build a PostToolUse-shaped stdin: tool_name + tool_input.file_path.
  local tool_name="$1" file_path="$2"
  jq -nc --arg t "$tool_name" --arg p "$file_path" \
    '{tool_name: $t, tool_input: {file_path: $p}}'
}

# ---------------------------------------------------------------------------
# AC22 — settings.json registration
# ---------------------------------------------------------------------------

@test "AC22 PostToolUse: settings.json registers knowledge-index.sh under Edit|Write" {
  [ -f "$SETTINGS_JSON" ]
  run jq -e '.hooks.PostToolUse[] | select(.matcher == "Edit|Write") | .hooks[] | select(.command | contains("knowledge-index.sh"))' "$SETTINGS_JSON"
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# AC10 — rebuild on corpus edit
# ---------------------------------------------------------------------------

@test "AC10: Edit on a knowledge .md triggers the builder and stderr says 'rebuilt'" {
  local input
  input=$(_hook_input "Edit" "plugins/agentic-dev-team/knowledge/owasp-detection.md")
  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ -e "$SENTINEL" ]
  [[ "$output" == *"[knowledge-index] rebuilt"* ]]
}

@test "AC10: Edit on a skills SKILL.md triggers the builder" {
  local input
  input=$(_hook_input "Edit" "plugins/agentic-dev-team/skills/specs/SKILL.md")
  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ -e "$SENTINEL" ]
}

@test "AC10: Write on a corpus file also triggers the builder" {
  local input
  input=$(_hook_input "Write" "plugins/agentic-dev-team/knowledge/owasp-detection.md")
  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ -e "$SENTINEL" ]
}

# ---------------------------------------------------------------------------
# AC11 — skip unrelated edits
# ---------------------------------------------------------------------------

@test "AC11: Edit on an agent file does NOT trigger the builder" {
  local input
  input=$(_hook_input "Edit" "plugins/agentic-dev-team/agents/security-review.md")
  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ ! -e "$SENTINEL" ]
  [[ "$output" != *"[knowledge-index]"* ]]
}

@test "AC11: Edit on a command file does NOT trigger" {
  local input
  input=$(_hook_input "Edit" "plugins/agentic-dev-team/commands/code-review.md")
  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ ! -e "$SENTINEL" ]
}

@test "AC11: Edit on a docs/ file does NOT trigger" {
  local input
  input=$(_hook_input "Edit" "plugins/agentic-dev-team/docs/agent-architecture.md")
  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ ! -e "$SENTINEL" ]
}

@test "AC11: Edit on knowledge/schemas/ does NOT trigger" {
  local input
  input=$(_hook_input "Edit" "plugins/agentic-dev-team/knowledge/schemas/foo.json")
  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ ! -e "$SENTINEL" ]
}

@test "AC11: Non-Edit/Write tool (e.g., Bash) is a no-op" {
  local input
  input=$(_hook_input "Bash" "plugins/agentic-dev-team/knowledge/owasp-detection.md")
  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ ! -e "$SENTINEL" ]
}

# ---------------------------------------------------------------------------
# AC12 — fail-open posture
# ---------------------------------------------------------------------------

@test "AC12: builder failure does not block the edit; stderr names 'rebuild failed'" {
  FAKE_BUILDER_MODE=fail
  export FAKE_BUILDER_MODE
  local input
  input=$(_hook_input "Edit" "plugins/agentic-dev-team/knowledge/owasp-detection.md")
  run bash -c "FAKE_BUILDER_MODE=fail echo '$input' | FAKE_BUILDER_MODE=fail bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[knowledge-index] rebuild failed"* ]]
}

@test "AC12: malformed stdin JSON exits 0 silently" {
  run bash -c "echo 'not json' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "AC12: missing tool_input.file_path exits 0 silently" {
  local input
  input=$(jq -nc '{tool_name: "Edit", tool_input: {}}')
  run bash -c "echo '$input' | bash '$HOOK' 2>&1 1>/dev/null"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}
