#!/usr/bin/env bats
# Tests for the runtime cost/token meter (issues #102, #170): transcript
# parsing, per-model + per-thread (main/subagent) attribution, token->dollar
# conversion via model-pricing.json, the append-only metrics log, regression
# detection, and the Stop hook wrapper.
#
# #170: attribution is limited to what the harness actually records — the model
# and the native `isSidechain` (main vs subagent). The per-command / per-phase /
# per-iteration buckets were removed because the harness exposes no such fields
# (see scripts spike) and a plugin cannot stamp them onto the transcript.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
METER="$REPO_ROOT/plugins/dev-team/hooks/lib/cost_meter.py"
HOOK="$REPO_ROOT/plugins/dev-team/hooks/cost_meter.py"

setup() {
  CASE="$(mktemp -d)"
  # Record 1: main-loop turn (no isSidechain) on opus.
  # Record 3: subagent turn (isSidechain:true) on sonnet.
  cat > "$CASE/t.jsonl" <<'EOF'
{"type":"assistant","message":{"model":"claude-opus-4-8","usage":{"input_tokens":10000,"output_tokens":2000,"cache_read_input_tokens":5000}}}
{"type":"user","message":{"content":"hi"}}
{"type":"assistant","isSidechain":true,"message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":8000,"output_tokens":1500,"cache_creation_input_tokens":3000}}}
EOF
}
teardown() { rm -rf "$CASE"; }

@test "meter: report attributes tokens per model and totals" {
  run python3 "$METER" report --transcript "$CASE/t.jsonl" --json
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.by_model."claude-opus-4-8".input_tokens')" = "10000" ]
  [ "$(echo "$output" | jq -r '.by_model."claude-sonnet-4-6".output_tokens')" = "1500" ]
  [ "$(echo "$output" | jq -r '.totals.input_tokens')" = "18000" ]
}

@test "meter: report splits spend by thread (main vs subagent via isSidechain)" {
  run python3 "$METER" report --transcript "$CASE/t.jsonl" --json
  [ "$status" -eq 0 ]
  # main-loop opus turn
  [ "$(echo "$output" | jq -r '.by_thread.main.input_tokens')" = "10000" ]
  # subagent sonnet turn
  [ "$(echo "$output" | jq -r '.by_thread.subagent.output_tokens')" = "1500" ]
}

@test "meter: the removed inert buckets are gone (#170)" {
  run python3 "$METER" report --transcript "$CASE/t.jsonl" --json
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r 'has("by_command")')" = "false" ]
  [ "$(echo "$output" | jq -r 'has("by_phase")')" = "false" ]
  [ "$(echo "$output" | jq -r 'has("by_iteration")')" = "false" ]
  [ "$(echo "$output" | jq -r 'has("by_agent")')" = "false" ]
}

@test "meter: dollar cost matches the pricing table" {
  run python3 "$METER" report --transcript "$CASE/t.jsonl" --json
  # opus: 10000/1e6*5 + 2000/1e6*25 + 5000/1e6*5*0.1 = 0.05+0.05+0.0025 = 0.1025
  [ "$(echo "$output" | jq -r '.by_model."claude-opus-4-8".cost_usd')" = "0.1025" ]
  # sonnet: 8000/1e6*3 + 1500/1e6*15 + 3000/1e6*3*1.25 = 0.024+0.0225+0.01125 = 0.05775
  [ "$(echo "$output" | jq -r '.by_model."claude-sonnet-4-6".cost_usd')" = "0.05775" ]
}

@test "meter: unknown model is flagged as unpriced (cost 0, not crash)" {
  echo '{"type":"assistant","message":{"model":"gpt-fake","usage":{"input_tokens":100,"output_tokens":10}}}' > "$CASE/u.jsonl"
  run python3 "$METER" report --transcript "$CASE/u.jsonl" --json
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.unpriced_models[0]')" = "gpt-fake" ]
  [ "$(echo "$output" | jq -r '.totals.cost_usd')" = "0.0" ]
}

@test "meter: record appends a session summary line with by_model and by_thread" {
  run python3 "$METER" record --transcript "$CASE/t.jsonl" --log "$CASE/log.jsonl"
  [ "$status" -eq 0 ]
  [ "$(wc -l < "$CASE/log.jsonl")" -eq 1 ]
  [ "$(jq -r '.total.messages' "$CASE/log.jsonl")" = "2" ]
  [ "$(jq -r '.by_model."claude-opus-4-8".input_tokens' "$CASE/log.jsonl")" = "10000" ]
  [ "$(jq -r '.by_thread.subagent.output_tokens' "$CASE/log.jsonl")" = "1500" ]
}

@test "meter: regression flags a cost spike, passes within tolerance" {
  printf '%s\n' '{"total":{"cost_usd":1.0}}' '{"total":{"cost_usd":1.1}}' > "$CASE/ok.jsonl"
  run python3 "$METER" regression --log "$CASE/ok.jsonl" --tolerance 0.5
  [ "$status" -eq 0 ]
  printf '%s\n' '{"total":{"cost_usd":1.0}}' '{"total":{"cost_usd":1.0}}' '{"total":{"cost_usd":5.0}}' > "$CASE/bad.jsonl"
  run python3 "$METER" regression --log "$CASE/bad.jsonl" --tolerance 0.5
  [ "$status" -eq 1 ]
  [[ "$output" == *"COST REGRESSION"* ]]
}

@test "meter: regression --window uses only recent priors" {
  # priors: 1,1,1, then a high 9; latest 5. All-time mean(1,1,1,9)=3 -> limit 4.5
  # -> 5 regresses. Windowed mean of last 1 prior (9) -> limit 13.5 -> 5 passes.
  printf '%s\n' '{"total":{"cost_usd":1.0}}' '{"total":{"cost_usd":1.0}}' \
    '{"total":{"cost_usd":1.0}}' '{"total":{"cost_usd":9.0}}' \
    '{"total":{"cost_usd":5.0}}' > "$CASE/w.jsonl"
  run python3 "$METER" regression --log "$CASE/w.jsonl" --tolerance 0.5
  [ "$status" -eq 1 ]
  run python3 "$METER" regression --log "$CASE/w.jsonl" --tolerance 0.5 --window 1
  [ "$status" -eq 0 ]
}

@test "hook: Stop payload writes a metrics line under cwd/metrics" {
  run bash -c "echo '{\"transcript_path\":\"$CASE/t.jsonl\",\"cwd\":\"$CASE\"}' | python3 '$HOOK'"
  [ "$status" -eq 0 ]
  [ -f "$CASE/metrics/cost-metering.jsonl" ]
}

@test "hook: DEV_TEAM_COST_METER=off is a no-op" {
  run bash -c "DEV_TEAM_COST_METER=off; export DEV_TEAM_COST_METER; echo '{\"transcript_path\":\"$CASE/t.jsonl\",\"cwd\":\"$CASE\"}' | python3 '$HOOK'"
  [ "$status" -eq 0 ]
  [ ! -f "$CASE/metrics/cost-metering.jsonl" ]
}

@test "hook: missing transcript fails open (exit 0, no write)" {
  run bash -c "echo '{\"transcript_path\":\"/nope/x.jsonl\",\"cwd\":\"$CASE\"}' | python3 '$HOOK'"
  [ "$status" -eq 0 ]
  [ ! -f "$CASE/metrics/cost-metering.jsonl" ]
}

@test "settings.json registers cost_meter.py on Stop and SubagentStop" {
  run jq -e '.hooks.Stop[].hooks[] | select(.command | contains("cost_meter.py"))' \
    "$REPO_ROOT/plugins/dev-team/settings.json"
  [ "$status" -eq 0 ]
  run jq -e '.hooks.SubagentStop[].hooks[] | select(.command | contains("cost_meter.py"))' \
    "$REPO_ROOT/plugins/dev-team/settings.json"
  [ "$status" -eq 0 ]
}
