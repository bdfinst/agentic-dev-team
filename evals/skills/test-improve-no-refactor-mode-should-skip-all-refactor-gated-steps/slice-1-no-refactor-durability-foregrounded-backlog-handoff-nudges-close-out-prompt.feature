Feature: /test-improve's no-refactor mode stays durable through Phase 6, and the deferred-refactor backlog is visible and actionable at close-out

  Scenario: Phase 6 threads the Phase-0 refactor-mode value into /quality-targets-converge
    Given phase-0.md recorded a refactor-mode value (no-refactor or refactor-allowed)
    When /test-improve dispatches Phase 6
    Then it invokes /quality-targets-converge with --refactor-mode <the recorded value> (in addition to --workflow test-improve)

  Scenario: quality-targets-converge does not propose a refactor action under no-refactor mode
    Given /quality-targets-converge is invoked with --refactor-mode no-refactor
    And the largest gap is a coverage gap on a file with no existing seam
    When the dispatch table picks the smallest action for that gap
    Then it writes a refactor-backlog.md entry instead of proposing a paired [Refactor-for-testability] Story

  Scenario: quality-targets-converge still proposes the refactor action under refactor-allowed mode
    Given /quality-targets-converge is invoked with --refactor-mode refactor-allowed
    And the largest gap is a coverage gap on a file with no existing seam
    When the dispatch table picks the smallest action for that gap
    Then it proposes a paired [Refactor-for-testability] Story (today's unchanged behavior)

  Scenario: quality-targets-converge defaults to refactor-allowed when the caller omits --refactor-mode, and says so
    Given /quality-targets-converge is invoked with no --refactor-mode flag
    When the dispatch table picks the smallest action for a no-seam coverage gap
    Then it falls back to refactor-allowed behavior (today's unconditional-propose default, for backward compatibility with callers other than /test-improve)
    And it prints "refactor-mode not specified by caller — defaulting to refactor-allowed" so the fallback is visible, not silent

  Scenario: the executive-summary template documents §7's expanded shape (documentation-shape, not a runtime-rendering check)
    Given the shipped executive-summary.md template
    Then its §7 header reads "Deferred work — areas requiring refactoring to add tests"
    And §7's body specifies a table with seam-needed / behavior-gained / estimated-risk columns sourced from refactor-backlog.md
    And §7 still documents the "_Not applicable — <reason>._" fallback for the empty case
    And the template still has exactly 10 numbered top-level sections

  Scenario Outline: /handoff is suggested only after context-heavy phase boundaries
    When <phase> completes
    Then /test-improve <expectation> the two-line /handoff + --from-phase suggestion

    Examples:
      | phase                              | expectation   |
      | Phase 1                            | prints        |
      | the Phase 4 end-of-phase review loop | prints        |
      | the Phase 5 end-of-phase review loop | prints        |
      | Phase 6                            | prints        |
      | Phase 2b                           | does NOT print |
      | Phase 3                            | does NOT print |
      | Phase 4b                           | does NOT print |

  Scenario: post-Phase-7 close-out prompt fires when a non-empty backlog remains and Phase 6 never asked
    Given refactor-backlog.md exists with at least one entry
    And Phase 6's coverage-driven [y/n] re-run prompt did not fire this run
    When Phase 7 completes
    Then /test-improve prompts "N REFACTOR_REQUIRED items remain backlogged. Re-run with refactor-allowed mode now? [y/n]" (N = the entry count)

  Scenario: post-Phase-7 close-out prompt is skipped when Phase 6 already asked
    Given refactor-backlog.md exists with at least one entry
    And phase-6.md records that its coverage-driven [y/n] re-run prompt already fired this run (regardless of the answer given)
    When Phase 7 completes
    Then /test-improve does NOT prompt again

  Scenario: post-Phase-7 close-out prompt is skipped when no backlog file exists
    Given refactor-backlog.md does not exist (no REFACTOR_REQUIRED items were ever backlogged this run)
    When Phase 7 completes
    Then /test-improve does NOT prompt

  Scenario: post-Phase-7 close-out prompt is skipped when the backlog file exists but is empty
    Given refactor-backlog.md exists with zero entries
    When Phase 7 completes
    Then /test-improve does NOT prompt
