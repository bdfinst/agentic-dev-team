#!/usr/bin/env bats
# Contract for the Cucumber-JVM BDD entry in the Spring Boot test stack profile
# (epic #443, issue #440).

PROFILE="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/test-stack-profiles/spring-boot.md"

@test "spring profile names Cucumber-JVM as a BDD runner" {
  grep -qi 'Cucumber-JVM' "$PROFILE"
}

@test "spring profile BDD entry references bdd-value-guide.md" {
  grep -q 'bdd-value-guide.md' "$PROFILE"
}

@test "spring profile cross-references bdd-frameworks.md" {
  grep -q 'bdd-frameworks.md' "$PROFILE"
}

@test "spring profile names both Maven and Gradle wiring" {
  grep -qi 'Maven' "$PROFILE"
  grep -qi 'Gradle' "$PROFILE"
}

@test "spring profile notes the cucumber-junit-platform-engine wiring" {
  grep -q 'cucumber-junit-platform-engine' "$PROFILE"
}

@test "spring profile preserves existing tools" {
  grep -q 'JUnit 5' "$PROFILE"
  grep -q 'SpringBootTest' "$PROFILE"
  grep -q 'Testcontainers' "$PROFILE"
  grep -Eq 'Pact|Spring Cloud Contract' "$PROFILE"
}
