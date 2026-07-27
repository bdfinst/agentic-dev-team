# Behavior spec for Slice 3 of the gherkin-derive comprehensive analysis default.
# Source of record: plans/gherkin-derive-comprehensive-analysis-default.md (Slice 3) · issue #1450
# Enforced by: tests/skills/test_gherkin_derive_skill.py
#
# This file is a Given/When/Then spec, not an eval-grader fixture (see
# evals/skills/README.md). Executable enforcement is the pytest contract
# named above.

Feature: gherkin-derive Step 5/6 analysis-coverage wiring

  Scenario: Step 5 requires the Analysis Coverage section in the inventory
    Given the gherkin-derive SKILL.md Step 5 section
    Then it requires an "## Analysis Coverage" section in gherkin.md listing
      all eight categories, each with found items or an explicit "none found"
      statement

  Scenario: Step 6 documents reporting the gate's three outcomes
    Given the gherkin-derive SKILL.md Step 6 section
    Then it documents invoking gherkin_analysis_coverage_gate.py and
      reporting its OK / N-missing / gate-did-not-run outcomes, mirroring
      how gherkin_stub_gate.py and gherkin_failure_path_gate.py are already
      reported
