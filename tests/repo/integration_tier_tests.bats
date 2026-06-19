#!/usr/bin/env bats
# Tests for the integration eval tier (issue #313): the `integration` grader
# (scripts/eval_graders/integration.py, via eval_grade.py), --check-corpus
# manifest validation, and the runner (scripts/run_integration_eval.py) worktree
# build/teardown + command recording. Hermetic — the runner self-test uses
# --skip-dispatch so no model is needed.

REPO="$BATS_TEST_DIRNAME/../.."
GRADE="$REPO/scripts/eval_grade.py"
RUNNER="$REPO/scripts/run_integration_eval.py"

setup() {
  T="$(mktemp -d)"
  mkdir -p "$T/expected" "$T/fixtures/demo"
  cat > "$T/expected/demo.json" <<'EOF'
{
  "fixture": "demo",
  "applicableSkills": ["orchestrator"],
  "integration": {
    "orchestrator": {
      "grader": "integration",
      "spec": "spec.md",
      "goldenRepo": "golden.tar.gz",
      "testCommands": ["true"]
    }
  }
}
EOF
  echo "do the thing" > "$T/fixtures/demo/spec.md"
  # Golden repo: one file; the test command `true` always exits 0.
  b="$(mktemp -d)"; echo "x" > "$b/file.txt"
  tar -czf "$T/fixtures/demo/golden.tar.gz" -C "$b" file.txt
  rm -rf "$b"
}
teardown() { rm -rf "$T"; }

# --- grader -----------------------------------------------------------------

@test "integration grader: all commands exit 0 -> PASS" {
  cat > "$T/actuals.json" <<'EOF'
{ "demo": { "integration": { "orchestrator": { "results": [
  { "command": "true", "exit_code": 0, "stderr_first_line": "" } ] } } } }
EOF
  run python3 "$GRADE" --expected-dir "$T/expected" --actuals "$T/actuals.json"
  [ "$status" -eq 0 ]
}

@test "integration grader: non-zero exit -> FAIL with command, exit, stderr" {
  cat > "$T/actuals.json" <<'EOF'
{ "demo": { "integration": { "orchestrator": { "results": [
  { "command": "npm test", "exit_code": 2, "stderr_first_line": "TypeError: boom" } ] } } } }
EOF
  run python3 "$GRADE" --expected-dir "$T/expected" --actuals "$T/actuals.json"
  [ "$status" -eq 1 ]
  [[ "$output" == *"'true'"* ]]              # declared command with no result
  cat > "$T/actuals2.json" <<'EOF'
{ "demo": { "integration": { "orchestrator": { "results": [
  { "command": "true", "exit_code": 2, "stderr_first_line": "TypeError: boom" } ] } } } }
EOF
  run python3 "$GRADE" --expected-dir "$T/expected" --actuals "$T/actuals2.json"
  [ "$status" -eq 1 ]
  [[ "$output" == *"exited 2"* ]]
  [[ "$output" == *"TypeError: boom"* ]]
}

@test "integration grader: missing result for a declared command -> FAIL" {
  cat > "$T/actuals.json" <<'EOF'
{ "demo": { "integration": { "orchestrator": { "results": [] } } } }
EOF
  run python3 "$GRADE" --expected-dir "$T/expected" --actuals "$T/actuals.json"
  [ "$status" -eq 1 ]
  [[ "$output" == *"no result recorded"* ]]
}

# --- corpus manifest validation ---------------------------------------------

@test "check-corpus: valid integration manifest passes" {
  run python3 "$GRADE" --check-corpus \
    --expected-dir "$T/expected" --fixtures-dir "$T/fixtures"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Eval corpus OK"* ]]
}

@test "check-corpus: integration entry missing goldenRepo fails" {
  cat > "$T/expected/demo.json" <<'EOF'
{ "fixture": "demo", "applicableSkills": ["orchestrator"],
  "integration": { "orchestrator": { "grader": "integration",
    "spec": "spec.md", "testCommands": ["true"] } } }
EOF
  run python3 "$GRADE" --check-corpus \
    --expected-dir "$T/expected" --fixtures-dir "$T/fixtures"
  [ "$status" -eq 2 ]
  [[ "$output" == *"missing 'goldenRepo'"* ]]
}

@test "check-corpus: integration entry with empty testCommands fails" {
  cat > "$T/expected/demo.json" <<'EOF'
{ "fixture": "demo", "applicableSkills": ["orchestrator"],
  "integration": { "orchestrator": { "grader": "integration",
    "spec": "spec.md", "goldenRepo": "golden.tar.gz", "testCommands": [] } } }
EOF
  run python3 "$GRADE" --check-corpus \
    --expected-dir "$T/expected" --fixtures-dir "$T/fixtures"
  [ "$status" -eq 2 ]
  [[ "$output" == *"non-empty testCommands"* ]]
}

# --- runner -----------------------------------------------------------------

@test "runner: --skip-dispatch builds worktree, runs command, records exit 0" {
  run python3 "$RUNNER" --skip-dispatch \
    --expected-dir "$T/expected" --fixtures-dir "$T/fixtures" \
    --out "$T/actuals.json"
  [ "$status" -eq 0 ]
  run jq -r '.demo.integration.orchestrator.results[0].exit_code' "$T/actuals.json"
  [ "$output" = "0" ]
  # And that actual grades PASS through the deterministic grader.
  run python3 "$GRADE" --expected-dir "$T/expected" --actuals "$T/actuals.json"
  [ "$status" -eq 0 ]
}

@test "runner: ephemeral worktree is torn down (no leftover temp dirs)" {
  before="$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'int-demo-*' 2>/dev/null | wc -l)"
  python3 "$RUNNER" --skip-dispatch \
    --expected-dir "$T/expected" --fixtures-dir "$T/fixtures" \
    --out "$T/actuals.json"
  after="$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'int-demo-*' 2>/dev/null | wc -l)"
  [ "$before" -eq "$after" ]
}

@test "runner: missing claude (no --skip-dispatch) errors naming the component" {
  # Restrict PATH so python3 + git resolve but claude does not.
  py="$(dirname "$(command -v python3)")"
  run env PATH="$py:/usr/bin:/bin" python3 "$RUNNER" \
    --expected-dir "$T/expected" --fixtures-dir "$T/fixtures" --out "$T/actuals.json"
  [ "$status" -eq 2 ]
  [[ "$output" == *"claude"* ]]
  [[ "$output" == *"prerequisites missing"* ]]
}
