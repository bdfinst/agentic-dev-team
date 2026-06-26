#!/usr/bin/env bats
# ci-changed-only.sh — the suite->watched-path mapping and change-matching logic
# behind ci-local.sh's --changed-only flag. The git interaction stays in
# ci-local.sh; the pure matching logic lives here so it is unit-testable without
# a contrived git history. These tests pin the match contract: directory
# prefixes, exact files, globs, unmapped (always-run) suites, and multi-file
# changesets.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
LIB="$REPO_ROOT/scripts/lib/ci-changed-only.sh"

setup() {
  # shellcheck source=/dev/null
  source "$LIB"
}

@test "lib sources cleanly and exposes the matcher" {
  type ci_suite_has_changes
  type ci_watched_paths
}

# --- directory-prefix watched paths ---------------------------------------

@test "dir-prefix path: a change under the directory runs the suite" {
  run ci_suite_has_changes chk_bats_repo "tests/repo/foo_tests.bats"
  [ "$status" -eq 0 ]
}

@test "dir-prefix path: a change outside every watched dir is skipped" {
  run ci_suite_has_changes chk_bats_repo "scripts/eval_grade.py"
  [ "$status" -eq 1 ]
}

@test "dir-prefix path: any one of several watched dirs matching runs it" {
  run ci_suite_has_changes chk_bats_content_rest "tests/docs/some_doc_test.bats"
  [ "$status" -eq 0 ]
}

# --- exact-file watched paths ---------------------------------------------

@test "exact-file path: the named file matches" {
  run ci_suite_has_changes chk_cost_regression "scripts/cost-regression-check.sh"
  [ "$status" -eq 0 ]
}

@test "exact-file path: a different file in the same dir does not match" {
  run ci_suite_has_changes chk_cost_regression "scripts/other-script.sh"
  [ "$status" -eq 1 ]
}

# --- glob watched paths ----------------------------------------------------

@test "glob path: a .js file anywhere matches the eslint suite" {
  run ci_suite_has_changes chk_eslint "some/nested/dir/app.js"
  [ "$status" -eq 0 ]
}

@test "glob path: a .ts file matches the eslint suite" {
  run ci_suite_has_changes chk_eslint "pkg/index.ts"
  [ "$status" -eq 0 ]
}

@test "glob path: a file outside every watched path is skipped" {
  run ci_suite_has_changes chk_eslint "README.md"
  [ "$status" -eq 1 ]
}

@test "glob path: the eslint dir-prefix arm matches a non-JS file under it" {
  run ci_suite_has_changes chk_eslint "plugins/dev-team/skills/foo/SKILL.md"
  [ "$status" -eq 0 ]
}

@test "glob path: the *.json arm matches a manifest change" {
  run ci_suite_has_changes chk_eslint "plugins/dev-team/.claude-plugin/plugin.json"
  [ "$status" -eq 0 ]
}

# Proves the set -f (noglob) guard is load-bearing: with real *.js files present
# in the working directory, an unquoted '*.js' watched entry would otherwise
# expand against the filesystem and stop matching the changed path. The matcher
# must still match 'app.js' (which does NOT exist on disk) via the glob.
@test "glob match is filesystem-independent (noglob guard)" {
  local d; d="$(mktemp -d)"
  : > "$d/decoy.js"
  run bash -c 'cd "$1" && . "$2" && ci_suite_has_changes chk_eslint "app.js"' _ "$d" "$LIB"
  rm -rf "$d"
  [ "$status" -eq 0 ]
}

# --- unmapped suites always run (conservative fallback) -------------------

@test "unmapped suite always runs (never silently skipped)" {
  run ci_suite_has_changes chk_oe_staleness "anything.txt"
  [ "$status" -eq 0 ]
}

@test "unmapped suite runs even with an empty changeset" {
  run ci_suite_has_changes chk_oe_staleness ""
  [ "$status" -eq 0 ]
}

# Pin the mapping table itself, independent of the matcher, so a misspelled or
# dropped suite key is caught directly (not just as a silent always-run).
@test "ci_watched_paths pins representative suite mappings" {
  [[ "$(ci_watched_paths chk_bats_repo)" == *"tests/repo/"* ]]
  [[ "$(ci_watched_paths chk_cost_regression)" == *"scripts/cost-regression-check.sh"* ]]
  [[ "$(ci_watched_paths chk_eslint)" == *"*.js"* ]]
  [ -z "$(ci_watched_paths chk_oe_staleness)" ]
}

# --- multi-file changesets -------------------------------------------------

@test "multi-file changeset: one matching file is enough to run" {
  run ci_suite_has_changes chk_model_routing "README.md plugins/dev-team/hooks/agent-model-resolve.sh"
  [ "$status" -eq 0 ]
}

@test "multi-file changeset: no matching file skips" {
  run ci_suite_has_changes chk_model_routing "README.md docs/notes.md"
  [ "$status" -eq 1 ]
}

# --- empty changeset -------------------------------------------------------

@test "empty changeset skips a mapped suite" {
  run ci_suite_has_changes chk_bats_repo ""
  [ "$status" -eq 1 ]
}
