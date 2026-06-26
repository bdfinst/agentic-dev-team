#!/usr/bin/env bats
# Slice 4 — test_modernization_review.py: artifact path resolution + phase 2/3/4/5 validators.
# Step 4.1: artifact resolution and phase 2 cross-reference
# Step 4.2: phase 3 schema check and phases 4/5 numeric validators

SCRIPT="$BATS_TEST_DIRNAME/../../scripts/test_modernization_review.py"

setup() {
  T="$(mktemp -d)"
  mkdir -p "$T/memory/test-modernize/my-repo"
  mkdir -p "$T/features/test-modernize"
}

teardown() {
  rm -rf "$T"
}

run_review() {
  python3 "$SCRIPT" --base-dir "$T" "$@"
}

# ---------------------------------------------------------------------------
# Artifact path resolution
# ---------------------------------------------------------------------------

@test "missing phase artifact exits 1 with 'not found' message" {
  run run_review --repo my-repo --phase 2
  [ "$status" -eq 1 ]
  [[ "$output" == *"not found"* ]]
}

# ---------------------------------------------------------------------------
# Phase 2 — Gherkin cross-reference
# ---------------------------------------------------------------------------

@test "phase 2: scenario in .feature not in gherkin-bindings.json exits 1 with scenario name" {
  cat > "$T/memory/test-modernize/my-repo/phase-2.md" <<'EOF'
# Phase 2 progress
EOF
  cat > "$T/features/test-modernize/login.feature" <<'EOF'
Feature: Login
  Scenario: login works
    Given a user exists
    When they log in
    Then they see the dashboard
EOF
  cat > "$T/memory/test-modernize/my-repo/gherkin-bindings.json" <<'EOF'
{}
EOF
  run run_review --repo my-repo --phase 2
  [ "$status" -eq 1 ]
  [[ "$output" == *"login works"* ]]
}

@test "phase 2: binding key not in any .feature exits 2 (warning for orphan)" {
  cat > "$T/memory/test-modernize/my-repo/phase-2.md" <<'EOF'
# Phase 2 progress
EOF
  # No .feature files — empty features dir
  cat > "$T/memory/test-modernize/my-repo/gherkin-bindings.json" <<'EOF'
{"orphan-scenario": {"file": "features/test-modernize/missing.feature", "step": 1}}
EOF
  run run_review --repo my-repo --phase 2
  [ "$status" -eq 2 ]
  [[ "$output" == *"orphan-scenario"* ]]
}

@test "phase 2: feature and binding match exits 0" {
  cat > "$T/memory/test-modernize/my-repo/phase-2.md" <<'EOF'
# Phase 2 progress
EOF
  cat > "$T/features/test-modernize/login.feature" <<'EOF'
Feature: Login
  Scenario: login works
    Given a user exists
    When they log in
    Then they see the dashboard
EOF
  cat > "$T/memory/test-modernize/my-repo/gherkin-bindings.json" <<'EOF'
{"login works": {"file": "features/test-modernize/login.feature", "step": 1}}
EOF
  run run_review --repo my-repo --phase 2
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Phase 3 — disabled-tests.json schema validation
# ---------------------------------------------------------------------------

@test "phase 3: entry missing 'reason' in disabled-tests.json exits 1" {
  cat > "$T/memory/test-modernize/my-repo/phase-3.md" <<'EOF'
# Phase 3 progress
Coverage: 80%
EOF
  cat > "$T/memory/test-modernize/my-repo/disabled-tests.json" <<'EOF'
[{"test": "FooTest", "skip_tag": "@skip-foo"}]
EOF
  run run_review --repo my-repo --phase 3
  [ "$status" -eq 1 ]
  [[ "$output" == *"reason"* ]]
}

@test "phase 3: entry missing 'skip_tag' in disabled-tests.json exits 1" {
  cat > "$T/memory/test-modernize/my-repo/phase-3.md" <<'EOF'
# Phase 3 progress
Coverage: 80%
EOF
  cat > "$T/memory/test-modernize/my-repo/disabled-tests.json" <<'EOF'
[{"test": "FooTest", "reason": "broken assertion"}]
EOF
  run run_review --repo my-repo --phase 3
  [ "$status" -eq 1 ]
  [[ "$output" == *"skip_tag"* ]]
}

@test "phase 3: valid disabled-tests.json exits 0" {
  cat > "$T/memory/test-modernize/my-repo/phase-3.md" <<'EOF'
# Phase 3 progress
Coverage: 80%
EOF
  cat > "$T/memory/test-modernize/my-repo/disabled-tests.json" <<'EOF'
[{"test": "FooTest", "reason": "broken assertion", "skip_tag": "@skip-foo"}]
EOF
  run run_review --repo my-repo --phase 3
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Phase 4 — coverage regression check
# ---------------------------------------------------------------------------

@test "phase 4: coverage in phase-4.md lower than phase-3.md baseline exits 1 with delta" {
  cat > "$T/memory/test-modernize/my-repo/phase-3.md" <<'EOF'
# Phase 3 progress
Coverage: 80%
EOF
  cat > "$T/memory/test-modernize/my-repo/phase-4.md" <<'EOF'
# Phase 4 progress
Coverage: 78%
EOF
  run run_review --repo my-repo --phase 4
  [ "$status" -eq 1 ]
  [[ "$output" == *"78"* ]] || [[ "$output" == *"80"* ]] || [[ "$output" == *"delta"* ]] || [[ "$output" == *"regression"* ]]
}

@test "phase 4: coverage same or higher than baseline exits 0" {
  cat > "$T/memory/test-modernize/my-repo/phase-3.md" <<'EOF'
# Phase 3 progress
Coverage: 80%
EOF
  cat > "$T/memory/test-modernize/my-repo/phase-4.md" <<'EOF'
# Phase 4 progress
Coverage: 85%
EOF
  run run_review --repo my-repo --phase 4
  [ "$status" -eq 0 ]
}

@test "phase 4: phase-3.md missing exits 1 with error finding baseline" {
  cat > "$T/memory/test-modernize/my-repo/phase-4.md" <<'EOF'
# Phase 4 progress
Coverage: 78%
EOF
  run run_review --repo my-repo --phase 4
  [ "$status" -eq 1 ]
  [[ "$output" == *"phase-3"* ]] || [[ "$output" == *"baseline"* ]]
}

# ---------------------------------------------------------------------------
# Phase 5 — quality targets validation
# ---------------------------------------------------------------------------

@test "phase 5: target missing 'measured_value' exits 1" {
  cat > "$T/memory/test-modernize/my-repo/phase-5.md" <<'EOF'
# Phase 5 progress

## Quality Targets
- target: coverage
  threshold: 80
  next_action: add tests for module X
EOF
  run run_review --repo my-repo --phase 5
  [ "$status" -eq 1 ]
  [[ "$output" == *"measured_value"* ]]
}

@test "phase 5: unmet target (value < threshold) without 'next_action' exits 1" {
  cat > "$T/memory/test-modernize/my-repo/phase-5.md" <<'EOF'
# Phase 5 progress

## Quality Targets
- target: coverage
  threshold: 80
  measured_value: 60
EOF
  run run_review --repo my-repo --phase 5
  [ "$status" -eq 1 ]
  [[ "$output" == *"next_action"* ]]
}

@test "phase 5: all targets met exits 0" {
  cat > "$T/memory/test-modernize/my-repo/phase-5.md" <<'EOF'
# Phase 5 progress

## Quality Targets
- target: coverage
  threshold: 80
  measured_value: 85
  next_action: none needed
EOF
  run run_review --repo my-repo --phase 5
  [ "$status" -eq 0 ]
}

@test "phase 5: unmet target with next_action exits 0" {
  cat > "$T/memory/test-modernize/my-repo/phase-5.md" <<'EOF'
# Phase 5 progress

## Quality Targets
- target: coverage
  threshold: 80
  measured_value: 75
  next_action: add tests for module X
EOF
  run run_review --repo my-repo --phase 5
  [ "$status" -eq 0 ]
}
