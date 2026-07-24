# Behavior spec for the descriptive-step-back-references change.
# Source of record: plans/descriptive-step-back-references.md (Slice 1) · issue #1396
# Enforced by: tests/skills/test_step_back_reference_labels.py
Feature: Step back-references name the step's action

  Scenario: cd-test-architecture's out-of-repo-test back-references are descriptive
    Given plugins/dev-team/skills/cd-test-architecture/SKILL.md
    When a paragraph refers back to Step 2b
    Then the reference names it as "locate and harvest out-of-repo tests"
    And no bare "(Step 2b)" with no accompanying description remains in the file

  Scenario: cd-test-architecture's Step 1 back-reference is descriptive
    Given plugins/dev-team/skills/cd-test-architecture/SKILL.md
    When a paragraph refers back to Step 1
    Then the reference names it as "inventory the application's components"

  Scenario: test-evaluation.md's out-of-repo-test back-references are descriptive
    Given plugins/dev-team/docs/test-evaluation.md
    When prose refers back to Step 2b before concluding a suite is untested
    Then the reference names it as "locate and harvest out-of-repo tests"
    And this holds at both the pre-heading mention (L62) and the behavior-inventory mention (L132)
    And no bare "(Step 2b)" with no accompanying description remains in the file

  Scenario: test-evaluation.md's cross-skill Farley-Score back-reference is descriptive
    Given plugins/dev-team/docs/test-evaluation.md
    When prose refers to /test-design's own Step 3 in the Farley Score reference-table row
    Then the reference names it as "Score the in-scope tests via Farley Score"
    And no bare "/test-design\` Step 3" with no accompanying description remains in the file

  Scenario: session-review's raw-log-tier back-references are corrected and descriptive
    Given plugins/dev-team/skills/session-review/SKILL.md
    When prose refers back to the gated raw-log tier
    Then the reference cites "Step 3b" (not "Step 2b")
    And names it "the raw-log semantic tier"
    And this holds at both the orchestrator-constraints mention (L33) and the methodology-lens mention (L241)

  Scenario: session-review's telemetry-sync back-references are corrected and descriptive
    Given plugins/dev-team/skills/session-review/SKILL.md
    When prose refers back to the cross-machine telemetry sync step
    Then the reference cites "Step 1" (not "Step 0")
    And names it "cross-machine telemetry sync"
    And this holds at both the Extract-step mention (L144) and the raw-log-tier mention (L202)

  Scenario: session-review's escalation-lever back-reference is descriptive
    Given plugins/dev-team/skills/session-review/SKILL.md
    When prose refers back to the Analyze step to describe where the escalation lever's hand-off is set
    Then the reference cites "Step 3"
    And names it "Analyze, digest-only"
    And no bare "in Step 3." with no accompanying description remains in the file

  Scenario: docker-image-audit's structural-analysis back-reference is descriptive
    Given plugins/dev-team/skills/docker-image-audit/SKILL.md
    When the hadolint-limitations paragraph refers back to Step 2b
    Then the reference names it as "Structural Analysis"
    And the two already-descriptive mentions (L24, L108) are unchanged

  Scenario: step headings are untouched
    Given any of the four edited files
    When its "### Step N" / "### N." headings are inspected
    Then their text is byte-identical to before this change
