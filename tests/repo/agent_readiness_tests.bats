#!/usr/bin/env bats
# Tests for the agent-readiness scanner MVP (issue #117).
# File-presence/heuristic scoring of a single local repo against the
# Agent-Readiness Scorecard, with weights/thresholds externalized to YAML.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCANNER="$REPO_ROOT/plugins/dev-team/skills/agent-readiness/scanner.py"
FIX="$REPO_ROOT/tests/fixtures/agent-readiness"

@test "scanner: minimal repo scores Agent-Hostile" {
  run python3 "$SCANNER" "$FIX/repo_minimal" --json "$BATS_TEST_TMPDIR/min.json"
  [ "$status" -eq 0 ]
  run jq -r '.tier' "$BATS_TEST_TMPDIR/min.json"
  [ "$output" = "Agent-Hostile" ]
}

@test "scanner: well-configured repo scores Agent-Ready with all MVP criteria at 2" {
  run python3 "$SCANNER" "$FIX/repo_well_configured" --json "$BATS_TEST_TMPDIR/wc.json"
  [ "$status" -eq 0 ]
  [ "$(jq -r '.tier' "$BATS_TEST_TMPDIR/wc.json")" = "Agent-Ready" ]
  # Every scored criterion is a 2.
  run jq '[.categories[].criteria[]?.score] | unique' "$BATS_TEST_TMPDIR/wc.json"
  [ "$output" = "[
  2
]" ]
}

@test "scanner: per-criterion evidence strings are present" {
  python3 "$SCANNER" "$FIX/repo_well_configured" --json "$BATS_TEST_TMPDIR/wc.json"
  run jq -r '.categories.documentation.criteria.D1_readme.evidence' "$BATS_TEST_TMPDIR/wc.json"
  [[ "$output" == *"README"* ]]
}

@test "scanner: deferred categories are reported, not scored" {
  python3 "$SCANNER" "$FIX/repo_minimal" --json "$BATS_TEST_TMPDIR/min.json"
  [ "$(jq -r '.categories.test_infrastructure.scored' "$BATS_TEST_TMPDIR/min.json")" = "false" ]
  [ "$(jq -r '.categories.type_safety.scored' "$BATS_TEST_TMPDIR/min.json")" = "false" ]
}

@test "scanner: B3 detects committed vs gitignored lock file" {
  # gitignored lock file -> score 1
  d="$BATS_TEST_TMPDIR/gi"; mkdir -p "$d"
  echo '{}' > "$d/package-lock.json"
  echo 'package-lock.json' > "$d/.gitignore"
  python3 "$SCANNER" "$d" --json "$d/r.json"
  [ "$(jq -r '.categories.build_env.criteria.B3_dependency_management.score' "$d/r.json")" = "1" ]
}

@test "scanner: acceptance — scoring this repo yields JSON with score + flags + Markdown" {
  run python3 "$SCANNER" "$REPO_ROOT" \
    --json "$BATS_TEST_TMPDIR/self.json" --markdown "$BATS_TEST_TMPDIR/self.md"
  [ "$status" -eq 0 ]
  # numeric overall score, a tier, and the manual-review flags array exist
  run jq -e '.overall_score | type == "number"' "$BATS_TEST_TMPDIR/self.json"
  [ "$status" -eq 0 ]
  run jq -e '.manual_review_flags | type == "array"' "$BATS_TEST_TMPDIR/self.json"
  [ "$status" -eq 0 ]
  grep -q "Agent-Readiness Report" "$BATS_TEST_TMPDIR/self.md"
}

@test "scanner: thresholds are externalized (config drives tier)" {
  # A custom config that makes every tier threshold 0 forces Agent-Ready.
  cfg="$BATS_TEST_TMPDIR/cfg.yaml"
  cat > "$cfg" <<'YAML'
version: "test"
weights: { documentation: 1.0 }
tiers: { agent_ready: 0, agent_assisted: 0, agent_limited: 0 }
criteria:
  documentation:
    D1_readme: { mvp: true }
thresholds: { readme_min_words: 200, ai_instructions_min_words: 100,
              file_size_p90_small: 300, file_size_p90_large: 500 }
source_extensions: [".py"]
exclude_dirs: [".git"]
YAML
  python3 "$SCANNER" "$FIX/repo_minimal" --config "$cfg" --json "$BATS_TEST_TMPDIR/r.json"
  [ "$(jq -r '.tier' "$BATS_TEST_TMPDIR/r.json")" = "Agent-Ready" ]
}
