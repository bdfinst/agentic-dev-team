# Behavior spec for /quality-targets-converge's mutation-history reuse rule.
# Source of record: plans/mutation-testing-every-phase.md (Slice 4) · issue #287
# Enforced by: tests/skills/test_quality_targets_converge_mutation_reuse.py
#
# This file is a Given/When/Then spec, not an eval-grader fixture (see
# evals/skills/README.md). Executable enforcement is the pytest contract named
# above; non-drift is checked by tests/repo/feature_spec_refs_test.bats.

Feature: /quality-targets-converge avoids re-measuring files Phase 4 already covered

  Scenario: every file with a recent history entry is reused, not re-measured
    Given mutation-history.json contains entries for src/order.ts (survivors_after=2) and src/payment.ts (survivors_after=0)
    And neither file was modified after its history entry's captured_at timestamp
    When /quality-targets-converge runs its measurement pass
    Then /mutation-testing is NOT invoked for src/order.ts or src/payment.ts
    And the surviving-mutant count for those files comes from mutation-history.json (latest entry per file)
    And the iteration's converge-<n>.json names the reuse explicitly: {reused_from_history:[src/order.ts, src/payment.ts]}

  Scenario: files modified after their last history entry are re-measured
    Given mutation-history.json has src/order.ts:survivors_after=2 captured at T0
    And src/order.ts was modified at T1 > T0 (per `git log`)
    When /quality-targets-converge runs its measurement pass
    Then /mutation-testing IS invoked scoped to src/order.ts
    And the result is written to mutation-history.json as a synthetic entry: {story:"converge-<n>", file:"src/order.ts", ...}
    And subsequent iterations within the same convergence run can reuse it

  Scenario: production-code files never touched in Phase 4 are measured fresh
    Given mutation-history.json has no entry for src/auth.ts
    And src/auth.ts is in the in-scope component list
    When /quality-targets-converge runs its measurement pass
    Then /mutation-testing is invoked scoped to src/auth.ts (with --workflow-managed-approval)
    And mutation-history.json gets a synthetic Phase-5 entry for src/auth.ts

  Scenario: status:tool_unavailable from a prior Phase-4 entry — re-attempt allowed
    Given mutation-history.json's latest entry for src/order.ts has status:"tool_unavailable"
    When /quality-targets-converge runs its measurement pass
    Then /mutation-testing IS invoked for src/order.ts (the tool may now be installed)
    And the new entry overrides the old for reuse purposes

  Scenario: converge-<n>.json reports reuse counts
    When the iteration completes
    Then converge-<n>.json has new fields: reused_from_history (count), measured_fresh (count), total_files (count)
    And the operator's report shows "mutation: reused N, measured M" so the cost saving is visible

  Scenario: existing Phase-5 contract unchanged when mutation-history is absent
    Given a /test-modernize run from before this change has no mutation-history.json
    When /quality-targets-converge runs
    Then it falls back to its current behavior (full /mutation-testing run on the in-scope components)
    And the SKILL.md documents this fallback explicitly so old runs aren't broken
