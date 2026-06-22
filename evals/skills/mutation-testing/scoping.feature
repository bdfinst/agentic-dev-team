# Behavior spec for /mutation-testing's scoped, workflow-callable mode.
# Source of record: plans/mutation-testing-every-phase.md (Slice 1) · issue #284
# Enforced by: tests/skills/mutation_testing_scoping_tests.bats
#
# This file is a Given/When/Then spec, not an eval-grader fixture: the
# mutation/coverage workflow skills are contract skills with no applicable
# verdict/skill_gate/integration grader genre, so their executable
# enforcement is the bats contract named above. It is kept here for strict
# acceptance-criteria traceability and is checked for non-drift by
# tests/repo/feature_spec_refs_test.bats.

Feature: mutation-testing exposes a scoped, workflow-callable mode

  Scenario: workflow caller scopes the run to a JS/TS file list and receives Stryker JSON
    Given a JS/TS repo with Stryker installed and a passing test suite
    And the project's primary language is detected as javascript
    When /mutation-testing is invoked with --scope src/calculator.ts --emit-json out/mut.json --workflow-managed-approval
    Then exit code is 0
    And mut.json.tool equals "stryker"
    And mut.json.scope equals ["src/calculator.ts"]
    And mut.json has keys ["schema_version","tool","scope","captured_at","total","killed","survived","equivalent","survivors"]
    And mut.json.survivors[] entries each have ["file","line","operator","status"] where status is "survived" or "equivalent"

  Scenario: Java caller scopes to a glob and receives pitest JSON
    Given a Maven repo with pitest configured
    And the project's primary language is detected as java
    When /mutation-testing is invoked with --scope "src/main/java/**/*.java" --emit-json out/mut.json --workflow-managed-approval
    Then exit code is 0
    And mut.json.tool equals "pitest"
    And mut.json.scope is the expanded file list

  Scenario: no tool installed — structured error, no partial JSON
    Given no mutation-testing tool is installed for the detected language
    When /mutation-testing is invoked with --scope src/foo.ts --emit-json out/mut.json --workflow-managed-approval
    Then exit code is non-zero
    And mut.json contains {"schema_version":1,"tool":null,"error":"no_tool_installed","language":"<detected>"}
    And no partial mutation run output is left in the project

  Scenario: --emit-json target directory unwritable
    Given /tmp/readonly is a read-only directory
    When /mutation-testing is invoked with --scope src/foo.ts --emit-json /tmp/readonly/mut.json --workflow-managed-approval
    Then exit code is non-zero
    And stderr names the unwritable path
    And no partial JSON is left on disk

  Scenario: --scope glob matches zero files
    Given no source file matches the glob "src/does-not-exist/*.ts"
    When /mutation-testing is invoked with --scope "src/does-not-exist/*.ts" --emit-json out/mut.json --workflow-managed-approval
    Then exit code is non-zero
    And mut.json contains {"schema_version":1,"tool":"<tool>","error":"empty_scope","scope_glob":"src/does-not-exist/*.ts"}

  Scenario: interactive mode is unchanged — prompt is observable
    Given /mutation-testing is invoked without --workflow-managed-approval
    When the tool's time-estimate exceeds the documented threshold
    Then stdout contains the literal string "Estimated time:"
    And the process blocks on stdin until the operator confirms

  Scenario: equivalent mutants are tagged so deltas don't double-count reclassifications
    When /mutation-testing emits JSON
    Then each survivor entry has status "survived" or "equivalent"
    And downstream callers can filter status="equivalent" before computing deltas
