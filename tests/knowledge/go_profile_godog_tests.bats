#!/usr/bin/env bats
# Contract for the Godog BDD entry in the Go test stack profile
# (epic #443, issue #437).

PROFILE="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/test-stack-profiles/go.md"

@test "go profile names Godog as a BDD runner" {
  grep -qi 'Godog' "$PROFILE"
}

@test "go profile BDD entry references bdd-value-guide.md" {
  grep -q 'bdd-value-guide.md' "$PROFILE"
}

@test "go profile cross-references bdd-frameworks.md for install" {
  grep -q 'bdd-frameworks.md' "$PROFILE"
}

@test "go profile notes Godog runs inside go test via TestSuite" {
  grep -Eqi 'godog\.TestSuite|inside .*go test|go test' "$PROFILE"
}

@test "go profile preserves existing tools" {
  grep -q 'httptest' "$PROFILE"
  grep -q 'Testcontainers-go' "$PROFILE"
  grep -q 'Pact-go' "$PROFILE"
  grep -q 'testing' "$PROFILE"
}
