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

# ---------------------------------------------------------------------------
# Slice 2 — agent-eval.yml workflow name + structural-gate delegation
# ---------------------------------------------------------------------------

# Extract the `structural-gate:` job block only. Range starts at the job
# heading and ends just before the next `  <name>:` job heading at the same
# indent level. Used to scope grep assertions so they don't accidentally match
# on other jobs in the same file.
structural_gate_block() {
  awk '
    /^  structural-gate:/ { flag=1; next }
    flag && /^  [a-z_-]+:[[:space:]]*$/ { flag=0 }
    flag { print }
  ' "$AGENT_EVAL"
}

@test "531-2.1a: agent-eval.yml declares 'name: Agent eval'" {
  run grep -c '^name: Agent eval$' "$AGENT_EVAL"
  [ "$status" -eq 0 ]
  [ "$output" -eq 1 ]
}

@test "531-2.1b: agent-eval.yml no longer declares 'name: Eval'" {
  count=$(grep -c '^name: Eval$' "$AGENT_EVAL" || true)
  [ "$count" -eq 0 ]
}

@test "531-2.1c: structural-gate has exactly one --only=chk_eval_corpus step" {
  block=$(structural_gate_block)
  count=$(echo "$block" | grep -c -- '--only=chk_eval_corpus' || true)
  [ "$count" -eq 1 ]
}

@test "531-2.1d: structural-gate has exactly one --only=chk_citation_lint step" {
  block=$(structural_gate_block)
  count=$(echo "$block" | grep -c -- '--only=chk_citation_lint' || true)
  [ "$count" -eq 1 ]
}

@test "531-2.1e: structural-gate no longer invokes 'scripts/eval_grade.py --check-corpus' directly" {
  block=$(structural_gate_block)
  count=$(echo "$block" | grep -c 'scripts/eval_grade.py --check-corpus' || true)
  [ "$count" -eq 0 ]
}

@test "531-2.1f: structural-gate no longer invokes 'scripts/citation_lint.py --all' directly" {
  block=$(structural_gate_block)
  count=$(echo "$block" | grep -c 'scripts/citation_lint.py --all' || true)
  [ "$count" -eq 0 ]
}

@test "531-2.1g: structural-gate preserves the bats step running eval_grader_tests.bats" {
  block=$(structural_gate_block)
  count=$(echo "$block" | grep -c 'eval_grader_tests.bats' || true)
  [ "$count" -ge 1 ]
}
