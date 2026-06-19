# Behavior spec for /test-modernize Phase 4's mutation halt prompt.
# Source of record: plans/mutation-testing-every-phase.md (Slice 3) · issue #286
# Enforced by: tests/skills/test_modernize_phase_4_mutation_tests.bats
#
# This file is a Given/When/Then spec, not an eval-grader fixture (see
# evals/skills/README.md). Executable enforcement is the bats contract named
# above; non-drift is checked by tests/repo/feature_spec_refs_test.bats.

Feature: /test-modernize Phase 4 surfaces mutation signal to the operator

  Scenario: Phase-4 Story closes with status:ok — workflow advances
    Given a [Component tests] Story S-1 closed by /build touching src/order.ts
    When /test-modernize invokes /coverage-delta --story S-1 --story-files src/order.ts
    And /coverage-delta returns status:"ok"
    Then the Story is marked closed in phase-4.md
    And the workflow advances to the next Story without prompting

  Scenario: Phase-4 Story closes with status:first_measurement — workflow advances with note
    Given a Story whose files have no prior mutation-history entry
    When /coverage-delta returns status:"first_measurement"
    Then the operator-visible report names this as the file's first measurement
    And the survivor count is logged but not gated
    And the workflow advances

  Scenario: Phase-4 Story close halted on net-new survivors with three documented actions
    Given /coverage-delta returns status:"net_new_survivors" listing src/order.ts:42 ConditionalBoundary (x>0 → x>=0) and src/order.ts:67 ReturnValue (return result → return null)
    When /test-modernize processes the result
    Then it pauses Story close and prints the documented halt prompt:
      """
      ⚠ Phase-4 Story <id> close halted — net-new surviving mutants on cited files

      Files this Story claims to test:
        - src/order.ts:42  ConditionalBoundary   x > 0  →  x >= 0
        - src/order.ts:67  ReturnValue           return result  →  return null

      Actions:
        [s] strengthen — add assertions, then re-run /coverage-delta --story <id> --story-files <files>
        [f] follow-up — open a Phase-5 [Strengthen assertions] Story citing these survivors
        [w] waive    — record reason; survivors carry into Phase 5

      Choose [s/f/w]:
      """
    And the workflow does not advance until the operator chooses

  Scenario: operator chooses 'waive' — reason recorded, workflow advances
    Given the halt prompt is showing for Story S-3
    When the operator types "w" and enters a reason
    Then the reason is appended to memory/test-modernize/<slug>/waivers.json as a Phase-4 waiver tagged with the survivor list
    And the Story closes
    And the workflow advances

  Scenario: operator chooses 'follow-up' — Phase-5 Story drafted, workflow advances
    Given the halt prompt is showing
    When the operator types "f"
    Then a draft Phase-5 [Strengthen assertions] Story is appended to phase-5.md citing the file:line:operator triples
    And the current Story closes
    And the workflow advances

  Scenario: operator chooses 'strengthen' — workflow waits for re-run
    Given the halt prompt is showing
    When the operator types "s"
    Then the workflow exits the current Story-close gate and waits
    And /continue (or re-invoking the same /coverage-delta call) re-enters at the same point

  Scenario: status:tool_unavailable — operator chooses install or skip
    Given /coverage-delta returns status:"tool_unavailable" with language:"javascript"
    When /test-modernize processes the result
    Then it prints: "Mutation tool unavailable for javascript. Install via /init-dev-team, or skip mutation gating for this run."
    And it offers actions [i] install via /init-dev-team, [k] skip — proceed advisory, [q] quit
    And on [k] the rest of Phase 4 runs without mutation gating and Phase 5 is notified

  Scenario: --story-files derived from /build's commit diff
    Given /build closed Story S-1 with commits modifying src/order.ts and test/order.test.ts
    When /test-modernize invokes /coverage-delta for S-1
    Then --story-files contains "src/order.ts" (production-code files only, tests filtered)
    And /test-modernize does NOT consult any tracker CLI for the file list

  Scenario: Phase 1, 2, 3 step text unchanged
    When the SKILL.md is read
    Then the Phase 1, Phase 2, and Phase 3 sections are unchanged from the prior version (excluding cross-references to mutation-history.json that point readers forward)
