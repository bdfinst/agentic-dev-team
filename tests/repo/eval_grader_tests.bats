#!/usr/bin/env bats
# Tests for scripts/eval_grade.py — the deterministic eval grader that backs
# the CI agent-eval gate (issue #99). The grader is model-free: it grades
# recorded agent/skill outputs ("actuals") against evals/expected/*.json
# exactly. These tests pin that grading + regression-vs-baseline behavior on
# a tiny self-contained corpus.

GRADER="$BATS_TEST_DIRNAME/../../scripts/eval_grade.py"

setup() {
  CASE="$(mktemp -d)"
  mkdir -p "$CASE/expected" "$CASE/fixtures"
  # One agent fixture: arch-review must FAIL with an error mentioning "layer".
  cat > "$CASE/expected/ar-demo.json" <<'EOF'
{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": {
    "arch-review": {
      "expectedStatus": "fail",
      "issueCount": { "min": 1, "max": 3 },
      "severities": { "error": { "min": 1, "max": 2 } },
      "mustMention": ["layer"],
      "mustNotMention": ["clean"]
    }
  }
}
EOF
  : > "$CASE/fixtures/ar-demo.ts"
}

teardown() { rm -rf "$CASE"; }

@test "grader: correct actual output grades PASS (exit 0)" {
  cat > "$CASE/actuals.json" <<'EOF'
{
  "ar-demo": {
    "agents": {
      "arch-review": {
        "status": "fail",
        "issues": [{ "severity": "error", "message": "domain imports infra layer" }],
        "summary": "layer violation"
      }
    }
  }
}
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" --actuals "$CASE/actuals.json"
  [ "$status" -eq 0 ]
}

@test "grader: wrong status grades FAIL with readable diff (exit 1)" {
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "pass", "issues": [], "summary": "looks clean" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" --actuals "$CASE/actuals.json"
  [ "$status" -eq 1 ]
  [[ "$output" == *"ar-demo::arch-review"* ]]
  [[ "$output" == *"status: expected 'fail', got 'pass'"* ]]
}

@test "grader: missing mustMention keyword fails" {
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "bad import" }],
  "summary": "" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" --actuals "$CASE/actuals.json"
  [ "$status" -eq 1 ]
  [[ "$output" == *"mustMention: missing 'layer'"* ]]
}

@test "grader: mustNotMention violation fails" {
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "layer is clean actually" }],
  "summary": "" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" --actuals "$CASE/actuals.json"
  [ "$status" -eq 1 ]
  [[ "$output" == *"mustNotMention: found forbidden 'clean'"* ]]
}

@test "grader: severity count out of range fails" {
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [
    { "severity": "error", "message": "layer a" },
    { "severity": "error", "message": "layer b" },
    { "severity": "error", "message": "layer c" }
  ],
  "summary": "" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" --actuals "$CASE/actuals.json"
  [ "$status" -eq 1 ]
  [[ "$output" == *"severities.error"* ]]
}

@test "grader: baseline isolates regressions — only baseline-passing pairs block" {
  # Baseline says arch-review WAS passing. A new failure is a [REGRESSION].
  echo '{ "passing": ["ar-demo::arch-review"] }' > "$CASE/baseline.json"
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "pass", "issues": [], "summary": "" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" \
    --actuals "$CASE/actuals.json" --baseline "$CASE/baseline.json"
  [ "$status" -eq 1 ]
  [[ "$output" == *"[REGRESSION]"* ]]
}

@test "grader: failure NOT in baseline does not block (exit 0)" {
  # Empty baseline: arch-review was never known-good, so a failure is not a
  # regression and must not red-line the gate.
  echo '{ "passing": [] }' > "$CASE/baseline.json"
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "pass", "issues": [], "summary": "" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" \
    --actuals "$CASE/actuals.json" --baseline "$CASE/baseline.json"
  [ "$status" -eq 0 ]
  [[ "$output" == *"No regressions against baseline."* ]]
}

@test "grader: --only scopes grading to the named agent (others skipped)" {
  # Add a second fixture for a different agent that WOULD fail, then scope to
  # arch-review only; the run must pass because nm-demo is not graded.
  cat > "$CASE/expected/nm-demo.json" <<'EOF'
{ "fixture": "nm-demo.ts", "applicableAgents": ["naming-review"],
  "agents": { "naming-review": { "expectedStatus": "fail" } } }
EOF
  : > "$CASE/fixtures/nm-demo.ts"
  cat > "$CASE/actuals.json" <<'EOF'
{
  "ar-demo": { "agents": { "arch-review": {
    "status": "fail",
    "issues": [{ "severity": "error", "message": "layer violation" }],
    "summary": "" } } },
  "nm-demo": { "agents": { "naming-review": { "status": "pass", "issues": [], "summary": "" } } }
}
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" \
    --actuals "$CASE/actuals.json" --only "arch-review"
  [ "$status" -eq 0 ]
  [[ "$output" == *"diff-scoped to: arch-review"* ]]
  [[ "$output" != *"nm-demo::naming-review"* ]]
}

@test "grader: empty --only grades everything" {
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "layer violation" }],
  "summary": "" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" \
    --actuals "$CASE/actuals.json" --only ""
  [ "$status" -eq 0 ]
}

@test "grader: --write-baseline records the passing pairs" {
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "layer violation" }],
  "summary": "" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" \
    --actuals "$CASE/actuals.json" --write-baseline "$CASE/baseline.json"
  [ "$status" -eq 0 ]
  [ -f "$CASE/baseline.json" ]
  run jq -r '.passing[0]' "$CASE/baseline.json"
  [ "$output" = "ar-demo::arch-review" ]
}

@test "grader: --check-corpus passes on a well-formed corpus" {
  run python3 "$GRADER" --check-corpus \
    --expected-dir "$CASE/expected" --fixtures-dir "$CASE/fixtures"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Eval corpus OK"* ]]
}

@test "grader: --check-corpus fails on invalid JSON" {
  echo '{ not json' > "$CASE/expected/broken.json"
  run python3 "$GRADER" --check-corpus \
    --expected-dir "$CASE/expected" --fixtures-dir "$CASE/fixtures"
  [ "$status" -eq 2 ]
  [[ "$output" == *"invalid JSON"* ]]
}

@test "grader: --check-corpus flags agents-block / applicableAgents drift" {
  cat > "$CASE/expected/drift.json" <<'EOF'
{
  "fixture": "drift.ts",
  "applicableAgents": ["arch-review"],
  "agents": { "naming-review": { "expectedStatus": "pass" } }
}
EOF
  : > "$CASE/fixtures/drift.ts"
  run python3 "$GRADER" --check-corpus \
    --expected-dir "$CASE/expected" --fixtures-dir "$CASE/fixtures"
  [ "$status" -eq 2 ]
  [[ "$output" == *"not in applicableAgents"* ]]
}
