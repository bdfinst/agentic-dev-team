#!/usr/bin/env bats
# Content contract for the per-language BDD wire-in reference
# (epic #443, issue #436). One section per language with the minimal steps to
# install and run a BDD runner.

REF="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/test-stack-profiles/bdd-frameworks.md"

@test "bdd-frameworks.md exists" {
  [ -f "$REF" ]
}

@test "covers all four languages / five sections (JS, Java Maven, Java Gradle, C#, Go)" {
  grep -Eqi 'Cucumber\.js' "$REF"          # JS/TS
  grep -Eqi 'Cucumber-JVM' "$REF"          # Java
  grep -Eqi '\bMaven\b' "$REF"
  grep -Eqi '\bGradle\b' "$REF"
  grep -Eqi 'Reqnroll' "$REF"              # C#
  grep -Eqi 'Godog' "$REF"                 # Go
}

@test "C# uses Reqnroll, not SpecFlow" {
  grep -qi 'Reqnroll' "$REF"
  # SpecFlow may be named only to say 'use Reqnroll instead'; must not be the recommendation.
  ! grep -Eqi 'use SpecFlow|recommend SpecFlow|SpecFlow\.xUnit' "$REF"
}

@test "each language documents an install command" {
  grep -Eq 'npm install .*@cucumber/cucumber' "$REF"
  grep -Eq 'cucumber-junit-platform-engine' "$REF"
  grep -Eq 'dotnet add package Reqnroll' "$REF"
  grep -Eq 'go get .*godog' "$REF"
}

@test "documents directory layout (features/ and step-defs)" {
  grep -Eq 'features/' "$REF"
  grep -Eqi 'step.def|step_definitions|support/|src/test/resources/features' "$REF"
}

@test "documents the per-language pending step stub shape" {
  grep -Eq 'this\.pending\(\)' "$REF"        # Cucumber.js
  grep -Eq 'PendingException' "$REF"         # Cucumber-JVM
  grep -Eq 'StepIsPending\(\)' "$REF"        # Reqnroll
  grep -Eq 'godog\.ErrPending' "$REF"        # Godog
}

@test "documents how to run and a CI/JUnit-XML note" {
  grep -Eqi 'run' "$REF"
  grep -Eqi 'JUnit XML|junit|CI' "$REF"
}
