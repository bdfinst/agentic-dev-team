#!/usr/bin/env bats
# Contract for the Reqnroll BDD entry in the .NET test stack profile
# (epic #443, issue #438).

PROFILE="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/test-stack-profiles/dotnet.md"

@test "dotnet profile names Reqnroll as a BDD runner" {
  grep -qi 'Reqnroll' "$PROFILE"
}

@test "dotnet profile BDD entry references bdd-value-guide.md" {
  grep -q 'bdd-value-guide.md' "$PROFILE"
}

@test "dotnet profile cross-references bdd-frameworks.md" {
  grep -q 'bdd-frameworks.md' "$PROFILE"
}

@test "dotnet profile prefers Reqnroll over SpecFlow with a license rationale" {
  grep -qi 'Reqnroll' "$PROFILE"
  grep -Eqi 'SpecFlow' "$PROFILE"
  grep -Eqi 'MIT|license|licen' "$PROFILE"
}

@test "dotnet profile preserves existing tools" {
  grep -q 'xUnit' "$PROFILE"
  grep -q 'WebApplicationFactory' "$PROFILE"
  grep -q 'Testcontainers-dotnet' "$PROFILE"
  grep -q 'PactNet' "$PROFILE"
  grep -q 'Playwright' "$PROFILE"
}
