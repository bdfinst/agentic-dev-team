# Behavior spec for Slice 3 of the adversarial dual-agent Gherkin quality review.
# Source of record: plans/adversarial-dual-agent-gherkin-quality-review.md (Slice 3) · issue #1452
# Enforced by: tests/skills/test_gherkin_public_quality_review_dispatch.py

Feature: gherkin-public dispatches independent Gherkin quality review

  Scenario: authored scenarios are reviewed before human sign-off
    Given a gherkin-public run that authored .feature files in Step 3
    When Step 4 (Cite the assessment) completes
    Then two gherkin-quality-critic Agent calls are issued in one message
    And this happens before Step 5 (Persist phase-2 progress) and before the
      Step 6 human sign-off

  Scenario: report separates agreed and single-source findings
    Given both agent instances returned at least one finding
    When Step 8 prints the report
    Then a distinct "Agreed Gherkin quality findings" section and a distinct
      "Single-source (unconfirmed) Gherkin quality findings" section both
      appear, separate from the components-flagged-for-hand-authoring callout
