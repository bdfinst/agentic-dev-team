#!/usr/bin/env bats
#
# Regression coverage for the workflow-audit fixes in issue #531:
#   - plugin-tests.yml renamed from "Tests" to "Plugin tests"
#   - agent-eval.yml renamed from "Eval" to "Agent eval" AND its
#     structural-gate job delegates two commands through
#     `bash scripts/ci-local.sh --only=chk_eval_corpus,chk_citation_lint`
#     rather than invoking them directly
#   - link-check.yml documents the intentional local/CI split for
#     chk_nav_integrity
#
# These assertions guard against a silent revert of the rename or a
# refactor that reintroduces the drift between ci-local.sh and the CI job.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
PLUGIN_TESTS="$REPO_ROOT/.github/workflows/plugin-tests.yml"
AGENT_EVAL="$REPO_ROOT/.github/workflows/agent-eval.yml"
LINK_CHECK="$REPO_ROOT/.github/workflows/link-check.yml"

# ---------------------------------------------------------------------------
# Slice 1 — plugin-tests.yml workflow name
# ---------------------------------------------------------------------------

@test "531-1.1a: plugin-tests.yml declares 'name: Plugin tests'" {
  run grep -c '^name: Plugin tests$' "$PLUGIN_TESTS"
  [ "$status" -eq 0 ]
  [ "$output" -eq 1 ]
}

@test "531-1.1b: plugin-tests.yml no longer declares 'name: Tests'" {
  # grep -c returns 0 when the pattern is not found — assert exactly zero matches.
  count=$(grep -c '^name: Tests$' "$PLUGIN_TESTS" || true)
  [ "$count" -eq 0 ]
}
