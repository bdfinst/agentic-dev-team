# Behavior spec for Slice 4 of the gherkin-derive comprehensive analysis default.
# Source of record: plans/gherkin-derive-comprehensive-analysis-default.md (Slice 4) · issue #1450
# Enforced by: tests/skills/test_gherkin_derive_1450_audit_notes.py
#
# This file is a Given/When/Then spec, not an eval-grader fixture (see
# evals/skills/README.md). Executable enforcement is the pytest contract
# named above.

Feature: gherkin-public and plan audit notes for issue #1450

  Scenario: gherkin-public documents why the depth directive doesn't transfer
    Given gherkin-public/SKILL.md's Notes section
    Then it explains this skill consumes a pre-built component map
      (/cd-test-architecture Phase 1) rather than discovering surfaces
      itself, so gherkin-derive's mandatory-depth paragraph does not
      transfer here without also touching /cd-test-architecture

  Scenario: plan documents why the depth directive doesn't transfer
    Given plan/SKILL.md's per-slice Gherkin authoring step
    Then it explains slice authoring is deliberately spec-scoped and
      exploration-bounded, so widening it into full controller/service/
      domain-logic discovery would contradict its own designed scope
