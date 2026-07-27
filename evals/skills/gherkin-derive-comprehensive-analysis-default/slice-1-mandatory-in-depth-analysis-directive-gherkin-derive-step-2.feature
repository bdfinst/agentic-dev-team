# Behavior spec for Slice 1 of the gherkin-derive comprehensive analysis default.
# Source of record: plans/gherkin-derive-comprehensive-analysis-default.md (Slice 1) · issue #1450
# Enforced by: tests/skills/test_gherkin_derive_skill.py
#
# This file is a Given/When/Then spec, not an eval-grader fixture (see
# evals/skills/README.md). Executable enforcement is the pytest contract
# named above.

Feature: gherkin-derive Step 2 mandatory analysis directive

  Scenario: SKILL.md names all eight required analysis categories unconditionally
    Given the gherkin-derive SKILL.md Step 2 section
    When a reader scans it for depth-of-analysis language
    Then it names controllers, handlers, services, domain logic, workflows,
      validation rules, error handling, and business processes
    And the directive is stated as mandatory/always-on, not optional or
      operator-configurable

  Scenario: existing discovery-cascade ordering is preserved
    Given the existing cascade-order test asserting OpenAPI < routes < tests
      < signatures
    When the new paragraph is appended after the cascade and the async sweep
    Then the existing test still passes unmodified
