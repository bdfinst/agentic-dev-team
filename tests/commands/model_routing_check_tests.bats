#!/usr/bin/env bats
# Tests for /model-routing-check — read-only diagnostic command (effort model).
# Side-effect-free; surfaces the band→model map, the ladder (or a starter),
# the session model, and recent routing bumps.

COMMAND_MD="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/model-routing-check/SKILL.md"
RESOLVER="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/model_resolve.py"

EXEC_SCRIPT=""

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  mkdir -p "$BATS_TMPDIR_CASE/knowledge" "$BATS_TMPDIR_CASE/.claude/metrics"
  cat > "$BATS_TMPDIR_CASE/knowledge/model-routing.json" <<'EOF'
{
  "low": "claude-haiku-4-5-20251001",
  "medium": "claude-sonnet-4-6",
  "high": "claude-opus-4-8",
  "haiku": "claude-haiku-4-5-20251001",
  "sonnet": "claude-sonnet-4-6",
  "opus": "claude-opus-4-8",
  "rounding": "round_half_up"
}
EOF
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/knowledge/model-routing.json"
  export MODEL_LADDER_JSON="$BATS_TMPDIR_CASE/.claude/model-ladder.json"
  export SESSION_MODEL_FILE="$BATS_TMPDIR_CASE/.claude/session-model"
  export MODEL_BUMP_LOG="$BATS_TMPDIR_CASE/.claude/metrics/model-routing.log"
  export MODEL_ROUTING_RESOLVER="$RESOLVER"  # test-only seam so the extracted exec block finds the helper
  EXEC_SCRIPT="$BATS_TMPDIR_CASE/run.sh"
  awk '/<!-- BEGIN EXEC -->/,/<!-- END EXEC -->/' "$COMMAND_MD" \
    | sed '/<!-- BEGIN EXEC -->/d;/<!-- END EXEC -->/d;/^```/d' \
    > "$EXEC_SCRIPT"
  chmod +x "$EXEC_SCRIPT"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset MODEL_ROUTING_JSON MODEL_LADDER_JSON SESSION_MODEL_FILE MODEL_BUMP_LOG MODEL_BUMP_TAIL
  unset MODEL_ROUTING_RESOLVER
}

_seed_bumps() {
  local n="$1"
  local i=0
  while (( i < n )); do
    printf '{"ts":"2026-06-01T12:%02d:00Z","band":"high","served":"claude-sonnet-4-6","reason":"effort","caller":"caller-%d","session":"claude-opus-4-8"}\n' "$i" "$i" >> "$MODEL_BUMP_LOG"
    i=$((i + 1))
  done
}

# ---------------------------------------------------------------------------
# Doc-inspection
# ---------------------------------------------------------------------------

@test "doc: command markdown file exists" {
  [ -f "$COMMAND_MD" ]
}

@test "doc: frontmatter declares name=model-routing-check and user-invocable" {
  run grep -E "^name:[[:space:]]+model-routing-check[[:space:]]*$" "$COMMAND_MD"
  [ "$status" -eq 0 ]
  run grep -E "^user-invocable:[[:space:]]+true[[:space:]]*$" "$COMMAND_MD"
  [ "$status" -eq 0 ]
}

@test "doc: allowed-tools lists Read and Bash" {
  run grep -E "^allowed-tools:.*Read.*Bash|^allowed-tools:.*Bash.*Read" "$COMMAND_MD"
  [ "$status" -eq 0 ]
}

@test "doc: body declares read-only, no side effects" {
  grep -qi "read-only" "$COMMAND_MD"
  grep -qi "no side effects" "$COMMAND_MD"
}

@test "doc: body documents the four required sections" {
  grep -q "band → model" "$COMMAND_MD"
  grep -q "Ladder" "$COMMAND_MD"
  grep -qi "Session model" "$COMMAND_MD"
  grep -qi "Recent routing bumps" "$COMMAND_MD"
}

@test "doc: body no longer references the retired probe or overrides file" {
  run grep -nE 'probe|model-overrides' "$COMMAND_MD"
  [ "$status" -ne 0 ]
}

@test "doc: body contains an executable block extractable by the test harness" {
  grep -q "<!-- BEGIN EXEC -->" "$COMMAND_MD"
  grep -q "<!-- END EXEC -->" "$COMMAND_MD"
  [ -s "$EXEC_SCRIPT" ]
}

# ---------------------------------------------------------------------------
# Behavioral: clean install (no ladder, no session, no log)
# ---------------------------------------------------------------------------

@test "clean: prints all three band→model pairs" {
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"low"*"claude-haiku-4-5-20251001"* ]]
  [[ "$output" == *"medium"*"claude-sonnet-4-6"* ]]
  [[ "$output" == *"high"*"claude-opus-4-8"* ]]
}

@test "clean: prints a starter ladder seeded from the defaults when none exists" {
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Ladder: none"* ]]
  [[ "$output" == *"Starter ladder"* ]]
  # The starter is the default map as a capability-ascending array.
  [[ "$output" == *'["claude-haiku-4-5-20251001","claude-sonnet-4-6","claude-opus-4-8"]'* ]]
}

@test "clean: session model reported unknown when not captured" {
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Session model: unknown"* ]]
}

@test "clean: recent bumps section says none recorded" {
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Recent routing bumps: none recorded"* ]]
}

@test "ladder present: reflected in the band→model map and printed" {
  echo '["claude-sonnet-4-6", "claude-opus-4-8"]' > "$MODEL_LADDER_JSON"
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Ladder: from"* ]]
  # low → bottom of ladder (sonnet) under the ladder.
  [[ "$output" == *"low"*"claude-sonnet-4-6"* ]]
}

@test "session model captured is printed" {
  printf 'claude-opus-4-8\n' > "$SESSION_MODEL_FILE"
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Session model: claude-opus-4-8"* ]]
}

@test "clean run is side-effect-free (file tree sha256 identical)" {
  local before after
  before=$(cd "$BATS_TMPDIR_CASE" && find . -type f | sort | xargs shasum -a 256 2>/dev/null | shasum -a 256)
  bash "$EXEC_SCRIPT" >/dev/null
  after=$(cd "$BATS_TMPDIR_CASE" && find . -type f | sort | xargs shasum -a 256 2>/dev/null | shasum -a 256)
  [ "$before" = "$after" ]
}

# ---------------------------------------------------------------------------
# Recent routing bumps
# ---------------------------------------------------------------------------

@test "three pre-seeded bumps are all printed" {
  _seed_bumps 3
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"caller-0"* ]]
  [[ "$output" == *"caller-1"* ]]
  [[ "$output" == *"caller-2"* ]]
}

@test "bump lines carry band, served, session, and caller" {
  _seed_bumps 1
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"high → claude-sonnet-4-6"* ]]
  [[ "$output" == *"[effort]"* ]]
  [[ "$output" == *"session=claude-opus-4-8"* ]]
  [[ "$output" == *"caller=caller-0"* ]]
}

@test "25 events default to last 10 + Showing-last-10 line" {
  _seed_bumps 25
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Showing last 10 of 25 bump events; raise MODEL_BUMP_TAIL to see more."* ]]
  [[ "$output" == *"caller=caller-15"* ]]
  [[ "$output" == *"caller=caller-24"* ]]
}

@test "MODEL_BUMP_TAIL=30 shows all 25, no Showing-last line" {
  _seed_bumps 25
  MODEL_BUMP_TAIL=30 run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"caller=caller-0"* ]]
  [[ "$output" == *"caller=caller-24"* ]]
  [[ "$output" != *"Showing last 10 of 25"* ]]
}
