#!/usr/bin/env bats
# Tests for scripts/eval_semver_classify.sh — the eval-corpus-as-semver
# classifier (issue #101). The pure functions are sourced and exercised
# directly; the end-to-end git flow is exercised in a throwaway repo.

SCRIPT="$BATS_TEST_DIRNAME/../../scripts/eval_semver_classify.sh"

setup() { source "$SCRIPT"; }

# --- classify_change_class ------------------------------------------------

@test "classify: no expected changes -> none" {
  run bash -c "source '$SCRIPT'; printf '' | classify_change_class"
  [ "$output" = "none" ]
}

@test "classify: only added expected files -> additive" {
  run bash -c "source '$SCRIPT'; printf 'A\tevals/expected/a.json\nA\tevals/expected/b.json\n' | classify_change_class"
  [ "$output" = "additive" ]
}

@test "classify: a modified expected file -> editing" {
  run bash -c "source '$SCRIPT'; printf 'A\tevals/expected/a.json\nM\tevals/expected/b.json\n' | classify_change_class"
  [ "$output" = "editing" ]
}

@test "classify: a deleted expected file -> editing" {
  run bash -c "source '$SCRIPT'; printf 'D\tevals/expected/b.json\n' | classify_change_class"
  [ "$output" = "editing" ]
}

@test "classify: a renamed expected file -> editing" {
  run bash -c "source '$SCRIPT'; printf 'R100\tevals/expected/a.json\tevals/expected/c.json\n' | classify_change_class"
  [ "$output" = "editing" ]
}

# --- class_to_min_bump ----------------------------------------------------

@test "min bump: editing -> major, additive -> minor, none -> patch" {
  [ "$(class_to_min_bump editing)" = "major" ]
  [ "$(class_to_min_bump additive)" = "minor" ]
  [ "$(class_to_min_bump none)" = "patch" ]
}

# --- detect_commit_bump ---------------------------------------------------

@test "detect: feat: -> minor" {
  run bash -c "source '$SCRIPT'; printf 'feat: add agent\n' | detect_commit_bump"
  [ "$output" = "minor" ]
}

@test "detect: feat(scope)!: -> major" {
  run bash -c "source '$SCRIPT'; printf 'feat(agents)!: change contract\n' | detect_commit_bump"
  [ "$output" = "major" ]
}

@test "detect: BREAKING CHANGE footer -> major" {
  run bash -c "source '$SCRIPT'; printf 'fix: tweak\n\nBREAKING CHANGE: alters expected\n' | detect_commit_bump"
  [ "$output" = "major" ]
}

@test "detect: fix/chore only -> patch" {
  run bash -c "source '$SCRIPT'; printf 'fix: typo\nchore: deps\n' | detect_commit_bump"
  [ "$output" = "patch" ]
}

@test "detect: strongest wins (feat then breaking) -> major" {
  run bash -c "source '$SCRIPT'; printf 'feat: a\nfeat!: b\n' | detect_commit_bump"
  [ "$output" = "major" ]
}

# --- class_to_min_bump: threshold (#136) ----------------------------------

@test "min bump: threshold -> minor (#136)" {
  [ "$(class_to_min_bump threshold)" = "minor" ]
}

# --- classify_expected_edit (#136) ----------------------------------------

@test "edit: only a tolerance changed -> threshold" {
  local base='{"applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":1}}}}'
  local head='{"applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":3}}}}'
  run bash -c "source '$SCRIPT'; classify_expected_edit '$base' '$head'"
  [ "$output" = "threshold" ]
}

@test "edit: a flipped expectedStatus -> flip" {
  local base='{"applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass"}}}'
  local head='{"applicableAgents":["a"],"agents":{"a":{"expectedStatus":"fail"}}}'
  run bash -c "source '$SCRIPT'; classify_expected_edit '$base' '$head'"
  [ "$output" = "flip" ]
}

@test "edit: an added applicable agent -> flip" {
  local base='{"applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass"}}}'
  local head='{"applicableAgents":["a","b"],"agents":{"a":{"expectedStatus":"pass"},"b":{"expectedStatus":"pass"}}}'
  run bash -c "source '$SCRIPT'; classify_expected_edit '$base' '$head'"
  [ "$output" = "flip" ]
}

@test "edit: a prose-only (description) change -> threshold" {
  local base='{"applicableAgents":["a"],"description":"old","agents":{"a":{"expectedStatus":"pass"}}}'
  local head='{"applicableAgents":["a"],"description":"new wording","agents":{"a":{"expectedStatus":"pass"}}}'
  run bash -c "source '$SCRIPT'; classify_expected_edit '$base' '$head'"
  [ "$output" = "threshold" ]
}

# --- end-to-end via a throwaway git repo ----------------------------------

_mkrepo() {
  REPO="$(mktemp -d)"
  cd "$REPO" || return 1
  git init -q
  git config user.email t@t.t
  git config user.name t
  git config commit.gpgsign false
  git config tag.gpgsign false
  mkdir -p evals/expected
  echo '{"fixture":"x.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"fail"}}}' \
    > evals/expected/x.json
  git add -A && git commit -q -m "chore: seed corpus"
  BASE=$(git rev-parse HEAD)
}

@test "e2e: editing an expected value without feat! FAILS" {
  _mkrepo
  echo '{"fixture":"x.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass"}}}' \
    > evals/expected/x.json
  git add -A && git commit -q -m "fix: tweak expectation"
  run bash "$SCRIPT" "$BASE" HEAD
  [ "$status" -eq 1 ]
  [[ "$output" == *"requires a 'major' bump"* ]]
  rm -rf "$REPO"
}

@test "e2e: editing an expected value WITH feat! passes" {
  _mkrepo
  echo '{"fixture":"x.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass"}}}' \
    > evals/expected/x.json
  git add -A && git commit -q -m "feat!: change a's expected status"
  run bash "$SCRIPT" "$BASE" HEAD
  [ "$status" -eq 0 ]
  [[ "$output" == *"OK:"* ]]
  rm -rf "$REPO"
}

@test "e2e: adding a new expected file WITH feat passes" {
  _mkrepo
  echo '{"fixture":"y.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"fail"}}}' \
    > evals/expected/y.json
  git add -A && git commit -q -m "feat: add fixture y"
  run bash "$SCRIPT" "$BASE" HEAD
  [ "$status" -eq 0 ]
  rm -rf "$REPO"
}

@test "e2e: adding a new expected file with only fix FAILS (needs minor)" {
  _mkrepo
  echo '{"fixture":"y.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"fail"}}}' \
    > evals/expected/y.json
  git add -A && git commit -q -m "fix: add fixture y"
  run bash "$SCRIPT" "$BASE" HEAD
  [ "$status" -eq 1 ]
  [[ "$output" == *"requires a 'minor' bump"* ]]
  rm -rf "$REPO"
}

@test "e2e: no corpus change with chore passes (patch)" {
  _mkrepo
  echo "unrelated" > README.md
  git add -A && git commit -q -m "chore: docs"
  run bash "$SCRIPT" "$BASE" HEAD
  [ "$status" -eq 0 ]
  rm -rf "$REPO"
}

# --- #136: threshold-only edits classify as minor, not major --------------

_mkrepo_thresh() {
  REPO="$(mktemp -d)"; cd "$REPO" || return 1
  git init -q; git config user.email t@t.t; git config user.name t
  git config commit.gpgsign false; git config tag.gpgsign false
  mkdir -p evals/expected
  echo '{"fixture":"x.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":1}}}}' \
    > evals/expected/x.json
  git add -A && git commit -q -m "chore: seed corpus"
  BASE=$(git rev-parse HEAD)
}

@test "e2e: a threshold-only edit needs only a minor bump (feat passes)" {
  _mkrepo_thresh
  echo '{"fixture":"x.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":3}}}}' \
    > evals/expected/x.json
  git add -A && git commit -q -m "feat: widen x tolerance"
  run bash "$SCRIPT" "$BASE" HEAD
  [ "$status" -eq 0 ]
  [[ "$output" == *"corpus change:     threshold"* ]]
  rm -rf "$REPO"
}

@test "e2e: a threshold-only edit with only fix FAILS (needs minor, not major)" {
  _mkrepo_thresh
  echo '{"fixture":"x.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":3}}}}' \
    > evals/expected/x.json
  git add -A && git commit -q -m "fix: widen x tolerance"
  run bash "$SCRIPT" "$BASE" HEAD
  [ "$status" -eq 1 ]
  [[ "$output" == *"requires a 'minor' bump"* ]]
  rm -rf "$REPO"
}

@test "e2e: a threshold-only edit does NOT demand a major bump" {
  _mkrepo_thresh
  echo '{"fixture":"x.ts","applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":3}}}}' \
    > evals/expected/x.json
  git add -A && git commit -q -m "feat: widen x tolerance"
  run bash "$SCRIPT" "$BASE" HEAD
  [[ "$output" != *"requires a 'major' bump"* ]]
  rm -rf "$REPO"
}

# --- #136: new review agent without a fixture is flagged ------------------

@test "e2e: a new *-review agent with no fixture FAILS" {
  _mkrepo
  mkdir -p plugins/dev-team/agents
  printf -- '---\nname: foo-review\nmodel: haiku\n---\n# Foo Review\n' \
    > plugins/dev-team/agents/foo-review.md
  git add -A && git commit -q -m "feat: add foo-review agent"
  run bash "$SCRIPT" "$BASE" HEAD
  [ "$status" -eq 1 ]
  [[ "$output" == *"without any eval fixture: foo-review"* ]]
  rm -rf "$REPO"
}

@test "e2e: a new *-review agent WITH a covering fixture passes" {
  _mkrepo
  mkdir -p plugins/dev-team/agents
  printf -- '---\nname: foo-review\nmodel: haiku\n---\n# Foo Review\n' \
    > plugins/dev-team/agents/foo-review.md
  echo '{"fixture":"f.ts","applicableAgents":["foo-review"],"agents":{"foo-review":{"expectedStatus":"fail"}}}' \
    > evals/expected/f.json
  git add -A && git commit -q -m "feat: add foo-review agent + fixture"
  run bash "$SCRIPT" "$BASE" HEAD
  [ "$status" -eq 0 ]
  rm -rf "$REPO"
}
