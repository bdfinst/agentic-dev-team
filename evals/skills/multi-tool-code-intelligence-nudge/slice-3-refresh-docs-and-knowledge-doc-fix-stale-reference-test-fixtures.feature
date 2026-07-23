# Behavior spec for Slice 3 of the multi-tool code-intelligence nudge.
# Source of record: plans/multi-tool-code-intelligence-nudge.md (Slice 3) · issue #1368
# Enforced by: tests/skills/test_multi_tool_code_intelligence_nudge_slice3.py
#
# This file is a Given/When/Then spec, not an eval-grader fixture (see
# evals/skills/README.md). The pytest contract named above is an INTERIM
# reference to the pre-existing tests/knowledge/test_codegraph_vs_graphify_doc.py
# suite until Slice 3 (Step 3.2) extends it with the doc-drift regression tests.

Feature: Documentation matches the multi-tool nudge behavior

  Scenario: The renamed mechanism doc names the three-tool behavior concretely
    Given plugins/dev-team/docs/code-intelligence-nudge.md has been rewritten
    When a reader or test greps the doc
    Then it contains the strings ".codegraph/", ".repowise/", "graphify-out/graph.json", and "tools_used", and no longer contains "codegraph-turn-mark.sh" or any reference implying CodeGraph is the only supported tool

  Scenario: The knowledge doc reflects current tool surfaces and routing precedence, with no drift back to retired tool names
    Given plugins/dev-team/knowledge/codegraph-vs-graphify.md has been refreshed
    When a reader or test greps the doc
    Then it contains a "Routing precedence" heading, contains "codegraph_explore", "get_health", and "get_dead_code", and does not contain "codegraph_context", "codegraph_callers", "codegraph_callees", or "codegraph_impact"

  Scenario: A regression test ties the hook's CUES tool names to the knowledge doc's prose
    Given the hook's CUES dict names "codegraph", "repowise", and "graphify"
    When plugins/dev-team/tests/knowledge/test_codegraph_vs_graphify_doc.py runs
    Then it asserts each tool's current entry-point name (codegraph_explore, get_context, graphify query) appears somewhere in the doc, failing loudly if a future CUES edit isn't mirrored there

  Scenario: No stale references to the renamed files remain
    Given all renames from Slices 1-2 are complete
    When scripts/check_md_references.py and the full pytest gate run
    Then neither reports a reference to codegraph_nudge.py, codegraph_turn_mark.py, codegraph-nudge.md, or codegraph-turn-state.json outside CHANGELOG.md/ADR history
