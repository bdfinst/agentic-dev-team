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

@test "grader: --write-baseline records the passing pairs (fresh file)" {
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
  # a measured run stamps provenance=measured (#133)
  run jq -r '.provenance' "$CASE/baseline.json"
  [ "$output" = "measured" ]
}

@test "baseline: shipped evals/baseline.json declares its provenance (#133)" {
  # Provenance must be honestly DECLARED — 'hand-authored' for the seed, or
  # 'measured' once a real harvest (eval_variance --write-baseline) has refreshed
  # it. The invariant is "honestly labelled", not "forever the seed value".
  run jq -r '.provenance' "$BATS_TEST_DIRNAME/../../evals/baseline.json"
  [ "$status" -eq 0 ]
  case "$output" in
    hand-authored|measured) : ;;
    *) echo "unexpected provenance: $output" >&2; return 1 ;;
  esac
}

@test "grader: --write-baseline MERGES, keeping untested pairs and adding new" {
  # Pre-existing baseline has a pair this run never touches; it must survive.
  echo '{ "passing": ["other-demo::naming-review"] }' > "$CASE/baseline.json"
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "layer violation" }],
  "summary": "" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" \
    --actuals "$CASE/actuals.json" --only "arch-review" \
    --write-baseline "$CASE/baseline.json"
  [ "$status" -eq 0 ]
  run jq -c '.passing' "$CASE/baseline.json"
  [ "$output" = '["ar-demo::arch-review","other-demo::naming-review"]' ]
}

@test "grader: --write-baseline drops a pair that was tested this run but now fails" {
  echo '{ "passing": ["ar-demo::arch-review","keep::naming-review"] }' > "$CASE/baseline.json"
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "pass", "issues": [], "summary": "" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" \
    --actuals "$CASE/actuals.json" --only "arch-review" \
    --write-baseline "$CASE/baseline.json"
  [ "$status" -eq 0 ]
  # arch-review failed this run -> removed; keep::naming-review untouched.
  run jq -c '.passing' "$CASE/baseline.json"
  [ "$output" = '["keep::naming-review"]' ]
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

# --- Pluggable grader registry (#309) ---------------------------------------

@test "registry: explicit grader: verdict grades identically to the default" {
  # Declaring the default grader explicitly must not change the verdict.
  cat > "$CASE/expected/ar-demo.json" <<'EOF'
{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": {
    "arch-review": {
      "grader": "verdict",
      "expectedStatus": "fail",
      "mustMention": ["layer"]
    }
  }
}
EOF
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "domain imports infra layer" }],
  "summary": "" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" --actuals "$CASE/actuals.json"
  [ "$status" -eq 0 ]
}

@test "registry: unknown grader fails grading with a readable diff (exit 1)" {
  cat > "$CASE/expected/ar-demo.json" <<'EOF'
{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": { "arch-review": { "grader": "made-up", "expectedStatus": "fail" } }
}
EOF
  cat > "$CASE/actuals.json" <<'EOF'
{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail", "issues": [], "summary": "" } } } }
EOF
  run python3 "$GRADER" --expected-dir "$CASE/expected" --actuals "$CASE/actuals.json"
  [ "$status" -eq 1 ]
  [[ "$output" == *"unknown grader 'made-up'"* ]]
}

@test "registry: --check-corpus rejects an unknown grader value (exit 2)" {
  cat > "$CASE/expected/ar-demo.json" <<'EOF'
{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": { "arch-review": { "grader": "nope", "expectedStatus": "fail" } }
}
EOF
  run python3 "$GRADER" --check-corpus \
    --expected-dir "$CASE/expected" --fixtures-dir "$CASE/fixtures"
  [ "$status" -eq 2 ]
  [[ "$output" == *"unknown grader 'nope'"* ]]
}

@test "registry: --check-corpus accepts a registered grader value (exit 0)" {
  cat > "$CASE/expected/ar-demo.json" <<'EOF'
{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": { "arch-review": { "grader": "verdict", "expectedStatus": "fail" } }
}
EOF
  run python3 "$GRADER" --check-corpus \
    --expected-dir "$CASE/expected" --fixtures-dir "$CASE/fixtures"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Eval corpus OK"* ]]
}
