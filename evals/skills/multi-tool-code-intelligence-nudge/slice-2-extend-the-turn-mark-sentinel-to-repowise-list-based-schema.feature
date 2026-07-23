# Behavior spec for Slice 2 of the multi-tool code-intelligence nudge.
# Source of record: plans/multi-tool-code-intelligence-nudge.md (Slice 2) · issue #1368
# Enforced by: tests/skills/test_multi_tool_code_intelligence_nudge_slice2.py
#
# This file is a Given/When/Then spec, not an eval-grader fixture (see
# evals/skills/README.md). The pytest contract named above is an INTERIM
# reference to the pre-rename plugins/dev-team/tests/hooks/test_codegraph_turn_mark.py
# suite until Slice 2 (Step 2.1) lands the code_intelligence_turn_mark.py rename.

Feature: Turn-mark sentinel covers Repowise alongside CodeGraph

  Scenario: A codegraph_* MCP tool call writes "codegraph" into the sentinel's tools_used list
    Given no sentinel file exists yet this turn
    When a "mcp__codegraph__explore" tool call completes
    Then the sentinel records transcript_id, turn_counter, and tools_used: ["codegraph"]

  Scenario: A repowise MCP tool call writes "repowise" into the sentinel's tools_used list
    Given no sentinel file exists yet this turn
    When a "mcp__plugin_repowise_repowise__get_context" tool call completes
    Then the sentinel records tools_used: ["repowise"]

  Scenario: Both tool families used in the same turn accumulate rather than overwrite
    Given the sentinel already records tools_used: ["codegraph"] for the current transcript/turn
    When a "mcp__plugin_repowise_repowise__get_risk" tool call completes
    Then the sentinel records tools_used: ["codegraph", "repowise"] for that same transcript/turn

  Scenario: A new turn (same transcript, new turn_counter) resets accumulation
    Given the sentinel records tools_used: ["codegraph"] for an earlier turn_counter on the same transcript_id
    When a "mcp__plugin_repowise_repowise__get_risk" tool call completes in a new turn
    Then the sentinel is rewritten with only tools_used: ["repowise"] for the new turn_counter

  Scenario: A new transcript_id at the same turn_counter also resets accumulation
    Given the sentinel records tools_used: ["codegraph"] for a different transcript_id at the same turn_counter
    When a "mcp__plugin_repowise_repowise__get_risk" tool call completes
    Then the sentinel is rewritten with only tools_used: ["repowise"] for the new transcript_id

  Scenario: The nudge hook suppresses only the families used this turn
    Given both ".codegraph/" and ".repowise/" exist, and a codegraph MCP tool was already called earlier this turn (only "codegraph" in tools_used)
    When a multi-file Grep call runs
    Then the composed message omits the CodeGraph line and includes only the Repowise line

  Scenario: Three indexed, two already used this turn — only the remaining tool's line shown
    Given ".codegraph/", ".repowise/", and "graphify-out/graph.json" all exist, and both a codegraph and a repowise MCP tool were already called earlier this turn
    When a multi-file Grep call runs
    Then the composed message names only Graphify, with no CodeGraph or Repowise line

  Scenario: All present tools already used this turn — full suppression
    Given both ".codegraph/" and ".repowise/" exist, and both a codegraph and a repowise MCP tool were already called earlier this turn
    When a multi-file Grep call runs
    Then the hook exits 0 with no output

  Scenario: Corrupt tools_used field fails open on the read side (nudge hook)
    Given the sentinel matches the current transcript/turn but its tools_used field is present and is not a list
    When a multi-file Grep call runs
    Then the sentinel is treated as if no tool was used this turn, and the hook does not crash

  Scenario: Legacy (pre-upgrade) sentinel schema fails open on the read side (nudge hook)
    Given the sentinel matches the current transcript/turn but has no tools_used field at all (the pre-Slice-2 schema)
    When a multi-file Grep call runs
    Then the sentinel is treated as if no tool was used this turn, and the hook does not crash

  Scenario: A repowise MCP tool call recovers from an already-corrupt sentinel on the write side (turn-mark hook)
    Given the sentinel file exists for the current transcript/turn but its tools_used field is present and is not a list
    When a "mcp__plugin_repowise_repowise__get_context" tool call completes
    Then the sentinel is rewritten with only tools_used: ["repowise"], and the write does not crash
