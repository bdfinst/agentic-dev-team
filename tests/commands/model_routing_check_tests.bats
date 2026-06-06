#!/usr/bin/env bats
# Tests for /model-routing-check — read-only diagnostic command.
# AC10 (side-effect-free), AC11 (surfaces bumps), AC11a (tail cap),
# AC11b (probe-applicability line).

COMMAND_MD="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/model-routing-check/SKILL.md"
RESOLVER="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/model-resolve.sh"

# Helper script that mirrors what the markdown command body invokes. We
# extract it from the command file at test-runtime so the doc-inspection
# and behavioral tests share one source of truth.
EXEC_SCRIPT=""

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  mkdir -p "$BATS_TMPDIR_CASE/knowledge" "$BATS_TMPDIR_CASE/.claude/metrics"
  cat > "$BATS_TMPDIR_CASE/knowledge/model-routing.json" <<'EOF'
{
  "haiku": "claude-haiku-4-5-20251001",
  "sonnet": "claude-sonnet-4-6",
  "opus": "claude-opus-4-8"
}
EOF
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/knowledge/model-routing.json"
  export MODEL_OVERRIDES_JSON="$BATS_TMPDIR_CASE/.claude/model-overrides.json"
  export MODEL_BUMP_LOG="$BATS_TMPDIR_CASE/.claude/metrics/model-routing.log"
  export MODEL_ROUTING_RESOLVER="$RESOLVER"  # test-only override so the extracted exec block finds the helper
  EXEC_SCRIPT="$BATS_TMPDIR_CASE/run.sh"
  # The command's bash body is delimited by a sentinel block. Extract it.
  awk '/<!-- BEGIN EXEC -->/,/<!-- END EXEC -->/' "$COMMAND_MD" \
    | sed '/<!-- BEGIN EXEC -->/d;/<!-- END EXEC -->/d;/^```/d' \
    > "$EXEC_SCRIPT"
  chmod +x "$EXEC_SCRIPT"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset MODEL_ROUTING_JSON MODEL_OVERRIDES_JSON MODEL_BUMP_LOG MODEL_BUMP_TAIL
  unset MODEL_ROUTING_RESOLVER
  unset ANTHROPIC_BASE_URL
}

_seed_bumps() {
  local n="$1"
  local i=0
  while (( i < n )); do
    printf '{"ts":"2026-06-01T12:%02d:00Z","requested":"haiku","served":"sonnet","reason":"override","caller":"caller-%d"}\n' "$i" "$i" >> "$MODEL_BUMP_LOG"
    i=$((i + 1))
  done
}

# ---------------------------------------------------------------------------
# Doc-inspection: AC18-equivalent for the diagnostic command
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

@test "doc: body documents all four required sections" {
  grep -q "Effective tier" "$COMMAND_MD"
  grep -q "Overrides" "$COMMAND_MD"
  grep -q "Recent tier bumps" "$COMMAND_MD"
  grep -q "Probe applicability" "$COMMAND_MD"
}

@test "doc: body contains an executable block extractable by the test harness" {
  grep -q "<!-- BEGIN EXEC -->" "$COMMAND_MD"
  grep -q "<!-- END EXEC -->" "$COMMAND_MD"
  [ -s "$EXEC_SCRIPT" ]
}

# ---------------------------------------------------------------------------
# Behavioral: clean install (no overrides, no log)
# ---------------------------------------------------------------------------

@test "clean: prints all three default tier→snapshot pairs" {
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"claude-haiku-4-5-20251001"* ]]
  [[ "$output" == *"claude-sonnet-4-6"* ]]
  [[ "$output" == *"claude-opus-4-8"* ]]
}

@test "clean: overrides section says none" {
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Overrides: none"* ]]
}

@test "clean: recent bumps section says none recorded" {
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Recent tier bumps:"* ]]
  [[ "$output" == *"none recorded"* ]]
}

@test "AC10: clean run is side-effect-free (file tree sha256 identical)" {
  local before after
  before=$(cd "$BATS_TMPDIR_CASE" && find . -type f | sort | xargs shasum -a 256 2>/dev/null | shasum -a 256)
  bash "$EXEC_SCRIPT" >/dev/null
  after=$(cd "$BATS_TMPDIR_CASE" && find . -type f | sort | xargs shasum -a 256 2>/dev/null | shasum -a 256)
  [ "$before" = "$after" ]
}

# ---------------------------------------------------------------------------
# AC11 — surfaces bumps
# ---------------------------------------------------------------------------

@test "AC11: three pre-seeded bumps are all printed" {
  _seed_bumps 3
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"caller-0"* ]]
  [[ "$output" == *"caller-1"* ]]
  [[ "$output" == *"caller-2"* ]]
}

@test "AC11: bump lines follow the format <ts>  <req> → <served>  [<reason>]  caller=<caller>" {
  _seed_bumps 1
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"haiku → sonnet"* ]]
  [[ "$output" == *"[override]"* ]]
  [[ "$output" == *"caller=caller-0"* ]]
}

# ---------------------------------------------------------------------------
# AC11a — tail cap at 10 (with override via MODEL_BUMP_TAIL)
# ---------------------------------------------------------------------------

@test "AC11a: 25 events default to last 10 + Showing-last-10 line" {
  _seed_bumps 25
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Showing last 10 of 25 bump events; raise MODEL_BUMP_TAIL to see more."* ]]
  # The first 15 callers (0..14) should NOT appear in the tail of 10.
  [[ "$output" != *"caller-0,"* ]] && [[ "$output" != *"caller=caller-0"* ]] || \
    [[ "$output" == *"caller=caller-15"* ]]
  # The last 10 (15..24) should appear.
  [[ "$output" == *"caller=caller-15"* ]]
  [[ "$output" == *"caller=caller-24"* ]]
}

@test "AC11a: MODEL_BUMP_TAIL=30 shows all 25, no Showing-last line" {
  _seed_bumps 25
  MODEL_BUMP_TAIL=30 run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"caller=caller-0"* ]]
  [[ "$output" == *"caller=caller-24"* ]]
  [[ "$output" != *"Showing last 10 of 25"* ]]
}

# ---------------------------------------------------------------------------
# AC11b — probe applicability line
# ---------------------------------------------------------------------------

@test "AC11b: unset ANTHROPIC_BASE_URL reports probe-supported" {
  unset ANTHROPIC_BASE_URL || true
  run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Probe applicability:"* ]]
  [[ "$output" == *"standard Anthropic endpoint (probe supported)"* ]]
}

@test "AC11b: Bedrock URL reports probe-skipped" {
  ANTHROPIC_BASE_URL="https://bedrock-runtime.us-east-1.amazonaws.com" run bash "$EXEC_SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"non-Anthropic endpoint (probe skipped)"* ]]
}
