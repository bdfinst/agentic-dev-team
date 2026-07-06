# Behavior spec for /coverage-delta's Phase-4 scoped-mutation measurement.
# Source of record: plans/mutation-testing-every-phase.md (Slice 2) · issue #285
# Enforced by: tests/skills/test_coverage_delta_mutation.py
#
# This file is a Given/When/Then spec, not an eval-grader fixture (see
# evals/skills/README.md). Executable enforcement is the pytest contract named
# above; non-drift is checked by tests/repo/feature_spec_refs_test.bats.

Feature: Phase-4 coverage-delta measures mutation on the Story's files; never gates

  Scenario: first measurement for a file establishes its baseline-of-record
    Given mutation-history.json has no prior entry for src/order.ts
    When /coverage-delta is invoked with --story S-1 --story-files src/order.ts
    Then /mutation-testing runs scoped to src/order.ts (with --workflow-managed-approval)
    And mutation-history.json gets an entry: {schema_version:1, story:"S-1", file:"src/order.ts", captured_at:<ISO>, survivors_before:null, survivors_after:N, delta:null, status:"first_measurement"}
    And /coverage-delta's JSON result block on stdout has status:"first_measurement"
    And exit code is 0

  Scenario: subsequent Story strengthens assertions — survivors drop
    Given the most recent mutation-history entry for src/order.ts has survivors_after=8
    When /coverage-delta is invoked with --story S-2 --story-files src/order.ts
    And /mutation-testing reports 3 surviving mutants on src/order.ts (after filtering status="equivalent")
    Then mutation-history gets an entry: {story:"S-2", file:"src/order.ts", survivors_before:8, survivors_after:3, delta:-5, status:"ok"}
    And the result block on stdout has status:"ok"
    And exit code is 0

  Scenario: Story executes code without asserting — net-new survivors
    Given the most recent mutation-history entry for src/order.ts has survivors_after=3
    When /coverage-delta is invoked with --story S-3 --story-files src/order.ts
    And /mutation-testing reports 5 surviving mutants on src/order.ts (after equivalent filter)
    Then mutation-history gets an entry with delta:2 and status:"net_new_survivors"
    And the result block on stdout has status:"net_new_survivors" and lists the new survivors by file:line:operator
    And exit code is 0 (the worker measures; it does not halt)

  Scenario: --story without --story-files — no mutation run, no history write
    Given /quality-targets-converge invokes /coverage-delta with --story S-4 and no --story-files
    When /coverage-delta runs
    Then no mutation tool is invoked by /coverage-delta itself
    And mutation-history.json is not appended to
    And the result block on stdout has mutation:null

  Scenario: --story-files glob matches zero files
    Given /build's commit diff produces an empty file list
    When /coverage-delta is invoked with --story S-5 --story-files ""
    Then no mutation run is triggered
    And mutation-history gets an entry: {story:"S-5", status:"skipped_empty_scope"}

  Scenario: mutation tool unavailable mid-run
    Given baseline coverage tooling is fine
    And no mutation-testing tool is installed for the detected language
    When /coverage-delta is invoked with --story S-6 --story-files src/order.ts
    Then /coverage-delta's result block has status:"tool_unavailable" and language:"<detected>"
    And mutation-history gets an entry: {story:"S-6", file:"src/order.ts", status:"tool_unavailable"}
    And exit code is 0
    And the result block names "/setup" as the installation path

  Scenario: tool present at one Story, absent at a later Story
    Given mutation-history shows a prior tool:"stryker" entry for src/order.ts
    And stryker is no longer on PATH
    When /coverage-delta is invoked with --story S-7 --story-files src/order.ts
    Then mutation-history records {story:"S-7", file:"src/order.ts", status:"tool_unavailable", prior_tool:"stryker"}
    And the result block surfaces both the disappearance and the prior tool name

  Scenario: parallel /coverage-delta invocations write atomically
    Given two [Component tests] Stories close within the same second
    When /coverage-delta is invoked for each in parallel
    Then both entries land in mutation-history.json
    And neither entry is truncated or interleaved
    And the file is written via temp-file-then-rename
