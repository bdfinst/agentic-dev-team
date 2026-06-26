#!/usr/bin/env bats
# Contract for the Cucumber.js BDD entry in the Node.js test stack profile
# (epic #443, issue #439).

PROFILE="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/test-stack-profiles/node.md"

@test "node profile names Cucumber.js as a BDD runner" {
  grep -qi 'Cucumber\.js' "$PROFILE"
}

@test "node profile BDD entry references bdd-value-guide.md" {
  grep -q 'bdd-value-guide.md' "$PROFILE"
}

@test "node profile cross-references bdd-frameworks.md" {
  grep -q 'bdd-frameworks.md' "$PROFILE"
}

@test "node profile clarifies Cucumber.js and Vitest/Jest are complementary" {
  grep -Eqi 'complement|not mutually exclusive|alongside|not.*alternativ' "$PROFILE"
}

@test "node profile preserves existing tools" {
  grep -Eq 'Vitest|Jest' "$PROFILE"
  grep -q 'supertest' "$PROFILE"
  grep -q 'MSW' "$PROFILE"
  grep -q 'Pact' "$PROFILE"
  grep -q 'Playwright' "$PROFILE"
}
