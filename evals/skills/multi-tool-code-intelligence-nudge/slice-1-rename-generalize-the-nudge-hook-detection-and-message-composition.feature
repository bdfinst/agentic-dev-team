# Behavior spec for Slice 1 of the multi-tool code-intelligence nudge.
# Source of record: plans/multi-tool-code-intelligence-nudge.md (Slice 1) · issue #1368
# Enforced by: tests/skills/test_multi_tool_code_intelligence_nudge_slice1.py
#
# This file is a Given/When/Then spec, not an eval-grader fixture (see
# evals/skills/README.md). Executable enforcement is the pytest contract named
# above, which re-runs plugins/dev-team/tests/hooks/test_code_intelligence_nudge.py.

Feature: Multi-tool code-intelligence nudge — detection and message composition

  Scenario: Only CodeGraph indexed — single-tool nudge (no regression)
    Given ".codegraph/" exists in the project and neither ".repowise/" nor "graphify-out/graph.json" exist
    When a multi-file Grep call runs
    Then the hook prints the single-tool CodeGraph nudge naming codegraph_explore with its differentiator clause, and the message mentions neither Repowise nor Graphify

  Scenario: Only Repowise indexed — single-tool nudge
    Given ".repowise/" exists and neither ".codegraph/" nor "graphify-out/graph.json" exist
    When a multi-file Glob call runs
    Then the hook prints a single-tool Repowise nudge naming get_context/get_risk/get_why with its differentiator clause, and the message mentions neither CodeGraph nor Graphify

  Scenario: Only Graphify indexed — single-tool nudge
    Given "graphify-out/graph.json" exists and neither ".codegraph/" nor ".repowise/" exist
    When a multi-file Grep call runs
    Then the hook prints a single-tool Graphify nudge naming graphify query with its differentiator clause, and the message mentions neither CodeGraph nor Repowise

  Scenario: Malformed stdin JSON fails open
    Given the hook receives invalid JSON on stdin
    When the hook runs
    Then it exits 0 with no output

  Scenario: graphify-out/ exists without graph.json — no Graphify nudge
    Given "graphify-out/" exists but "graphify-out/graph.json" does not, and neither ".codegraph/" nor ".repowise/" exist
    When a multi-file Grep call runs
    Then the hook exits 0 with no output

  Scenario: Two indexed — combined nudge in fixed precedence order
    Given both ".codegraph/" and ".repowise/" exist, and neither has been used yet this turn
    When a multi-file Grep call runs
    Then the hook prints one combined message listing Repowise before CodeGraph (precedence order: Graphify, Repowise, CodeGraph), each with its cue and differentiator, prefixed by a disambiguation line

  Scenario: All three indexed — combined nudge names all three in precedence order
    Given ".codegraph/", ".repowise/", and "graphify-out/graph.json" all exist, and none has been used yet this turn
    When a multi-file Grep call runs
    Then the hook prints one combined message listing Graphify, then Repowise, then CodeGraph, in that order

  Scenario: None indexed — silent
    Given none of ".codegraph/", ".repowise/", "graphify-out/graph.json" exist
    When a multi-file Grep call runs
    Then the hook exits 0 with no output

  Scenario: Read never nudges
    Given ".codegraph/" and "graphify-out/graph.json" both exist
    When a Read call runs
    Then the hook exits 0 with no output

  Scenario: Single-file Grep never nudges
    Given ".codegraph/" and "graphify-out/graph.json" both exist
    When a Grep call with an explicit file `path` runs
    Then the hook exits 0 with no output

  Scenario: Literal-pattern Glob never nudges
    Given ".codegraph/" and "graphify-out/graph.json" both exist
    When a Glob call with a literal (non-metacharacter) `pattern` runs
    Then the hook exits 0 with no output

  Scenario: CodeGraph already used this turn — suppressed from a two-tool message
    Given both ".codegraph/" and "graphify-out/graph.json" exist, and a codegraph MCP tool was already called earlier this turn
    When a multi-file Grep call runs
    Then the composed message omits the CodeGraph line and includes only the Graphify line

  Scenario: Graphify path is unreadable or the wrong type — fails open
    Given "graphify-out/graph.json" is a directory instead of a regular file
    When a multi-file Grep call runs
    Then Graphify is treated as not present, the hook does not crash, and no other tool's line is affected

  Scenario: Repowise path is the wrong type — fails open
    Given ".repowise" exists but is a regular file, not a directory
    When a multi-file Grep call runs
    Then Repowise is treated as not present and the hook does not crash

  Scenario: /careful mode blocks a pending nudge
    Given ".codegraph/" exists and /careful mode is active
    When a multi-file Grep call runs
    Then the hook exits 2 and the message carries "[blocked by /careful]"
