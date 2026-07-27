# Behavior spec for Slice 2 of the adversarial dual-agent Gherkin quality review.
# Source of record: plans/adversarial-dual-agent-gherkin-quality-review.md (Slice 2) · issue #1452
# Enforced by: tests/skills/test_gherkin_derive_quality_review_dispatch.py

Feature: gherkin-derive dispatches independent Gherkin quality review

  Scenario: non-none mode with written scenarios dispatches two independent agents
    Given a gherkin-derive run in xunit-with-annotations or bdd-runner mode
    And at least one .feature file was written or merged this run
    When Step 5 (Output) completes
    Then two gherkin-quality-critic Agent calls are issued in one message
    And neither call's prompt contains the other call's output
    And this happens before Step 6's report

  Scenario: none mode skips the dispatch
    Given a gherkin-derive run in none mode
    Then no gherkin-quality-critic agent is dispatched

  Scenario: report separates agreed and single-source findings
    Given both agent instances returned at least one finding
    When Step 6 prints the report
    Then a distinct "Agreed Gherkin quality findings" section lists findings
      both instances raised for the same feature file and title
    And a distinct "Single-source (unconfirmed) Gherkin quality findings"
      section lists findings only one instance raised
    And neither section is folded into the characterization, possibly-stale,
      title-mismatch, or skipped-duplicate callouts

  Scenario: zero findings from both instances still prints both sections
    Given neither agent instance raised any finding
    When Step 6 prints the report
    Then both sections still print, each reading
      "None — both instances raised no findings"

  Scenario: one instance fails or returns unparseable output
    Given one gherkin-quality-critic call errored, timed out, or returned
      JSON that could not be parsed
    When Step 6 prints the report
    Then the run does not crash and treats that instance's findings as empty
    And the report states "one review instance did not return usable output
      — findings below are single-source only"
    And no finding from the failed instance is silently promoted to agreed
