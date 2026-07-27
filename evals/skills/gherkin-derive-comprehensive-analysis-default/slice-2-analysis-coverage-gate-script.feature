# Behavior spec for Slice 2 of the gherkin-derive comprehensive analysis default.
# Source of record: plans/gherkin-derive-comprehensive-analysis-default.md (Slice 2) · issue #1450
# Enforced by: tests/skills/test_gherkin_analysis_coverage_gate_behavior.py
#
# This file is a Given/When/Then spec, not an eval-grader fixture (see
# evals/skills/README.md). Executable enforcement is the pytest contract
# named above, which re-runs
# plugins/dev-team/tests/scripts/test_gherkin_analysis_coverage_gate.py's
# full unit coverage.

Feature: gherkin_analysis_coverage_gate.py

  Scenario: all eight categories recorded
    Given a gherkin.md inventory with all eight Analysis Coverage categories
      populated (found items or an explicit "none found" line)
    When the gate runs
    Then it exits 0

  Scenario: a category is missing or present-but-empty
    Given a gherkin.md inventory missing (or with an empty) "domain logic" entry
    When the gate runs with --json
    Then it exits 1
    And the JSON payload lists "domain logic" among the missing categories

  Scenario: no Analysis Coverage section found
    Given a gherkin.md file with no "## Analysis Coverage" heading
    When the gate runs
    Then it exits 2, distinct from the exit-1 "found problems" case
