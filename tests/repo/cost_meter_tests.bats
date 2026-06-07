#!/usr/bin/env bats
# Tests for the runtime cost/token meter (issue #102): transcript parsing,
# per-agent attribution, token->dollar conversion via model-pricing.json, the
# append-only metrics log, regression detection, and the Stop hook wrapper.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
METER="$REPO_ROOT/plugins/dev-team/hooks/lib/cost_meter.py"
HOOK="$REPO_ROOT/plugins/dev-team/hooks/cost-meter.sh"

setup() {
  CASE="$(mktemp -d)"
  cat > "$CASE/t.jsonl" <<'EOF'
{"type":"assistant","message":{"model":"claude-opus-4-8","usage":{"input_tokens":10000,"output_tokens":2000,"cache_read_input_tokens":5000}}}
{"type":"user","message":{"content":"hi"}}
{"type":"assistant","agent_type":"security-review","message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":8000,"output_tokens":1500,"cache_creation_input_tokens":3000}}}
EOF
}
teardown() { rm -rf "$CASE"; }

@test "meter: report attributes tokens per agent and totals" {
  run python3 "$METER" report --transcript "$CASE/t.jsonl" --json
  [ "$status" -eq 0 ]
  # opus on orchestrator: 10000 in, 2000 out
  [ "$(echo "$output" | jq -r '.by_agent.orchestrator.input_tokens')" = "10000" ]
  # subagent attributed to security-review
  [ "$(echo "$output" | jq -r '.by_agent."security-review".output_tokens')" = "1500" ]
  [ "$(echo "$output" | jq -r '.totals.input_tokens')" = "18000" ]
}

@test "meter: dollar cost matches the pricing table" {
  run python3 "$METER" report --transcript "$CASE/t.jsonl" --json
  # opus: 10000/1e6*5 + 2000/1e6*25 + 5000/1e6*5*0.1 = 0.05+0.05+0.0025 = 0.1025
  [ "$(echo "$output" | jq -r '.by_agent.orchestrator.cost_usd')" = "0.1025" ]
  # sonnet: 8000/1e6*3 + 1500/1e6*15 + 3000/1e6*3*1.25 = 0.024+0.0225+0.01125 = 0.05775
  [ "$(echo "$output" | jq -r '.by_agent."security-review".cost_usd')" = "0.05775" ]
}

@test "meter: unknown model is flagged as unpriced (cost 0, not crash)" {
  echo '{"type":"assistant","message":{"model":"gpt-fake","usage":{"input_tokens":100,"output_tokens":10}}}' > "$CASE/u.jsonl"
  run python3 "$METER" report --transcript "$CASE/u.jsonl" --json
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.unpriced_models[0]')" = "gpt-fake" ]
  [ "$(echo "$output" | jq -r '.totals.cost_usd')" = "0.0" ]
}

@test "meter: record appends a session summary line" {
  run python3 "$METER" record --transcript "$CASE/t.jsonl" --log "$CASE/log.jsonl"
  [ "$status" -eq 0 ]
  [ "$(wc -l < "$CASE/log.jsonl")" -eq 1 ]
  run jq -r '.total.messages' "$CASE/log.jsonl"
  [ "$output" = "2" ]
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

@test "hook: Stop payload writes a metrics line under cwd/metrics" {
  run bash -c "echo '{\"transcript_path\":\"$CASE/t.jsonl\",\"cwd\":\"$CASE\"}' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -f "$CASE/metrics/cost-metering.jsonl" ]
}

@test "hook: DEV_TEAM_COST_METER=off is a no-op" {
  run bash -c "DEV_TEAM_COST_METER=off; export DEV_TEAM_COST_METER; echo '{\"transcript_path\":\"$CASE/t.jsonl\",\"cwd\":\"$CASE\"}' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ ! -f "$CASE/metrics/cost-metering.jsonl" ]
}

@test "hook: missing transcript fails open (exit 0, no write)" {
  run bash -c "echo '{\"transcript_path\":\"/nope/x.jsonl\",\"cwd\":\"$CASE\"}' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ ! -f "$CASE/metrics/cost-metering.jsonl" ]
}

@test "meter: attributes spend per command via attributionSkill (#134)" {
  cat > "$CASE/cmd.jsonl" <<'EOF'
{"type":"assistant","attributionSkill":"code-review","message":{"model":"claude-opus-4-8","usage":{"input_tokens":10000,"output_tokens":2000}}}
{"type":"assistant","attributionSkill":"build","message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":4000,"output_tokens":500}}}
{"type":"assistant","message":{"model":"claude-haiku-4-5","usage":{"input_tokens":100,"output_tokens":10}}}
EOF
  run python3 "$METER" report --transcript "$CASE/cmd.jsonl" --json
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.by_command."code-review".input_tokens')" = "10000" ]
  [ "$(echo "$output" | jq -r '.by_command.build.output_tokens')" = "500" ]
  # records with no skill tag fall into "untagged", not lost
  [ "$(echo "$output" | jq -r '.by_command.untagged.input_tokens')" = "100" ]
}

@test "meter: attributes spend per fix-loop iteration (#134)" {
  cat > "$CASE/iter.jsonl" <<'EOF'
{"type":"assistant","attributionSkill":"code-review","fixLoopIteration":1,"message":{"model":"claude-opus-4-8","usage":{"input_tokens":10000,"output_tokens":2000}}}
{"type":"assistant","attributionSkill":"code-review","fixLoopIteration":2,"message":{"model":"claude-opus-4-8","usage":{"input_tokens":6000,"output_tokens":1000}}}
{"type":"assistant","message":{"model":"claude-opus-4-8","usage":{"input_tokens":500,"output_tokens":50}}}
EOF
  run python3 "$METER" report --transcript "$CASE/iter.jsonl" --json
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.by_iteration."1".input_tokens')" = "10000" ]
  [ "$(echo "$output" | jq -r '.by_iteration."2".input_tokens')" = "6000" ]
  # un-marked records degrade to "unattributed"
  [ "$(echo "$output" | jq -r '.by_iteration.unattributed.input_tokens')" = "500" ]
}

@test "meter: attributes spend per orchestration phase (#139)" {
  cat > "$CASE/phase.jsonl" <<'EOF'
{"type":"assistant","attributionSkill":"build","message":{"model":"claude-opus-4-8","usage":{"input_tokens":8000,"output_tokens":1000}}}
{"type":"assistant","attributionSkill":"code-review","message":{"model":"claude-opus-4-8","usage":{"input_tokens":5000,"output_tokens":600}}}
{"type":"assistant","attributionSkill":"review-agent","message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":3000,"output_tokens":200}}}
{"type":"assistant","orchestrationPhase":"specs","message":{"model":"claude-opus-4-8","usage":{"input_tokens":1000,"output_tokens":100}}}
EOF
  run python3 "$METER" report --transcript "$CASE/phase.jsonl" --json
  [ "$status" -eq 0 ]
  # build phase from /build
  [ "$(echo "$output" | jq -r '.by_phase.build.input_tokens')" = "8000" ]
  # review phase aggregates code-review + review-agent: 5000+3000
  [ "$(echo "$output" | jq -r '.by_phase.review.input_tokens')" = "8000" ]
  # explicit orchestrationPhase marker wins
  [ "$(echo "$output" | jq -r '.by_phase.specs.input_tokens')" = "1000" ]
}

@test "meter: record persists by_command and by_iteration (#134)" {
  cat > "$CASE/iter.jsonl" <<'EOF'
{"type":"assistant","attributionSkill":"code-review","fixLoopIteration":1,"message":{"model":"claude-opus-4-8","usage":{"input_tokens":10000,"output_tokens":2000}}}
EOF
  run python3 "$METER" record --transcript "$CASE/iter.jsonl" --log "$CASE/log.jsonl"
  [ "$status" -eq 0 ]
  run jq -r '.by_command."code-review".input_tokens' "$CASE/log.jsonl"
  [ "$output" = "10000" ]
  run jq -r '.by_iteration."1".output_tokens' "$CASE/log.jsonl"
  [ "$output" = "2000" ]
}

@test "meter: regression --window uses only recent priors (#134)" {
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

@test "settings.json registers cost-meter.sh on Stop and SubagentStop" {
  run jq -e '.hooks.Stop[].hooks[] | select(.command | contains("cost-meter.sh"))' \
    "$REPO_ROOT/plugins/dev-team/settings.json"
  [ "$status" -eq 0 ]
  run jq -e '.hooks.SubagentStop[].hooks[] | select(.command | contains("cost-meter.sh"))' \
    "$REPO_ROOT/plugins/dev-team/settings.json"
  [ "$status" -eq 0 ]
}
