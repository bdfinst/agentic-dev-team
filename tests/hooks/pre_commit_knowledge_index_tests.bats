#!/usr/bin/env bats
# Tests for hooks/pre-commit-knowledge-index.sh — sibling PreToolUse:Bash
# hook that blocks `git commit` when the working-tree index is stale.
# Also covers hooks/lib/pre-commit-detect.sh (shared with pre-commit-review.sh).
#
# AC13, AC13a, AC14, AC15, AC22 (PreToolUse half).

HOOK="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/pre-commit-knowledge-index.sh"
DETECT_LIB="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/pre-commit-detect.sh"
SETTINGS_JSON="$BATS_TEST_DIRNAME/../../plugins/dev-team/settings.json"

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  # Build a tiny temp git repo. The hook reads `git diff --cached` to
  # decide which corpus files are staged, so the test repo needs the
  # plugin layout.
  cd "$BATS_TMPDIR_CASE"
  git init -q
  git config user.email "test@example.com"
  git config user.name "Test"
  mkdir -p plugins/dev-team/{knowledge,skills/specs,agents,hooks/lib}
  cat > plugins/dev-team/knowledge/foo.md <<'EOF'
# Foo
## Section A
First sentence of A.
EOF
  cat > plugins/dev-team/agents/some-agent.md <<'EOF'
# Some Agent
## Section
Body.
EOF
  # Copy the shared helper + builder + hook so the test rig is fully
  # self-contained (we run from the temp repo's working dir).
  mkdir -p plugins/dev-team/hooks/lib
  cp "$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/knowledge-index-paths.sh" plugins/dev-team/hooks/lib/
  cp "$DETECT_LIB" plugins/dev-team/hooks/lib/
  cp "$HOOK" plugins/dev-team/hooks/
  cp "$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/build-knowledge-index.sh" plugins/dev-team/hooks/lib/
  # The shell wrapper exec's the Python builder; copy it too so the
  # exec'd path exists inside the temp repo's plugin tree.
  cp "$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/build_knowledge_index.py" plugins/dev-team/hooks/lib/

  # Initial commit so HEAD exists.
  git add -A
  git commit -q -m "initial"

  # Build the index against the temp repo and stage it.
  bash plugins/dev-team/hooks/lib/build-knowledge-index.sh
  git add plugins/dev-team/knowledge/index.json
}

teardown() {
  cd /
  rm -rf "$BATS_TMPDIR_CASE"
}

_bash_input() {
  jq -nc --arg c "$1" '{tool_name: "Bash", tool_input: {command: $c}}'
}

# ---------------------------------------------------------------------------
# Shared helper: pre-commit-detect.sh
# ---------------------------------------------------------------------------

@test "detect: _is_git_commit_invocation matches 'git commit -m' invocations" {
  run bash -c "source '$DETECT_LIB' && _is_git_commit_invocation 'git commit -m foo'"
  [ "$status" -eq 0 ]
}

@test "detect: _is_git_commit_invocation rejects non-commit commands" {
  run bash -c "source '$DETECT_LIB' && _is_git_commit_invocation 'git status'"
  [ "$status" -eq 1 ]
  run bash -c "source '$DETECT_LIB' && _is_git_commit_invocation 'git push'"
  [ "$status" -eq 1 ]
  run bash -c "source '$DETECT_LIB' && _is_git_commit_invocation 'ls -la'"
  [ "$status" -eq 1 ]
}

@test "detect: --no-verify is treated as bypass" {
  run bash -c "source '$DETECT_LIB' && _is_git_commit_invocation 'git commit --no-verify -m foo'"
  [ "$status" -eq 1 ]
}

# ---------------------------------------------------------------------------
# AC22 — settings.json registration
# ---------------------------------------------------------------------------

@test "AC22 PreToolUse: settings.json registers pre-commit-knowledge-index.sh under Bash" {
  [ -f "$SETTINGS_JSON" ]
  run jq -e '.hooks.PreToolUse[] | select(.matcher == "Bash") | .hooks[] | select(.command | contains("pre-commit-knowledge-index.sh"))' "$SETTINGS_JSON"
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# AC15 — skip when no corpus file is staged
# ---------------------------------------------------------------------------

@test "AC15: non-commit bash invocations are silent no-ops" {
  local input
  input=$(_bash_input "ls -la")
  run bash -c "cd '$BATS_TMPDIR_CASE' && echo '$input' | bash plugins/dev-team/hooks/pre-commit-knowledge-index.sh 2>&1"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "AC15: commit with only non-corpus files staged is allowed" {
  # Edit and stage an agent file only.
  cd "$BATS_TMPDIR_CASE"
  echo "## New" >> plugins/dev-team/agents/some-agent.md
  echo "Body." >> plugins/dev-team/agents/some-agent.md
  git add plugins/dev-team/agents/some-agent.md

  local input
  input=$(_bash_input "git commit -m test")
  run bash -c "cd '$BATS_TMPDIR_CASE' && echo '$input' | bash plugins/dev-team/hooks/pre-commit-knowledge-index.sh 2>&1"
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# AC14 — pass when working-tree index matches sources
# ---------------------------------------------------------------------------

@test "AC14: commit with corpus + matching index staged exits 0" {
  cd "$BATS_TMPDIR_CASE"
  # Edit a corpus file, rebuild the index, stage both.
  echo "## New Section" >> plugins/dev-team/knowledge/foo.md
  echo "Body of new section." >> plugins/dev-team/knowledge/foo.md
  bash plugins/dev-team/hooks/lib/build-knowledge-index.sh
  git add plugins/dev-team/knowledge/foo.md plugins/dev-team/knowledge/index.json

  local input
  input=$(_bash_input "git commit -m 'add section'")
  run bash -c "cd '$BATS_TMPDIR_CASE' && echo '$input' | bash plugins/dev-team/hooks/pre-commit-knowledge-index.sh 2>&1"
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# AC13 — block when working-tree index is stale
# ---------------------------------------------------------------------------

@test "AC13: commit with stale index blocks with the two-line remediation" {
  cd "$BATS_TMPDIR_CASE"
  # Edit the corpus file but DO NOT rebuild the index.
  echo "## New Section" >> plugins/dev-team/knowledge/foo.md
  echo "Body of new section." >> plugins/dev-team/knowledge/foo.md
  git add plugins/dev-team/knowledge/foo.md

  local input
  input=$(_bash_input "git commit -m 'add section'")
  run bash -c "cd '$BATS_TMPDIR_CASE' && echo '$input' | bash plugins/dev-team/hooks/pre-commit-knowledge-index.sh 2>&1"
  [ "$status" -eq 2 ]
  # Headline
  [[ "$output" == *"knowledge/index.json is stale"* ]]
  # Two-line remediation
  [[ "$output" == *"bash plugins/dev-team/hooks/lib/build-knowledge-index.sh"* ]]
  [[ "$output" == *"git add plugins/dev-team/knowledge/index.json"* ]]
}

# ---------------------------------------------------------------------------
# AC13a — block working-tree drift past the staged pair
# ---------------------------------------------------------------------------

@test "AC13a: commit blocks when working tree drifts past a consistent staged pair" {
  cd "$BATS_TMPDIR_CASE"
  # 1. Stage corpus + matching index.
  echo "## First" >> plugins/dev-team/knowledge/foo.md
  echo "Body of first." >> plugins/dev-team/knowledge/foo.md
  bash plugins/dev-team/hooks/lib/build-knowledge-index.sh
  git add plugins/dev-team/knowledge/foo.md plugins/dev-team/knowledge/index.json
  # 2. Re-edit the working tree without re-staging.
  echo "## Second" >> plugins/dev-team/knowledge/foo.md
  echo "Body of second." >> plugins/dev-team/knowledge/foo.md
  # working-tree index now stale relative to working-tree foo.md

  local input
  input=$(_bash_input "git commit -m 'add sections'")
  run bash -c "cd '$BATS_TMPDIR_CASE' && echo '$input' | bash plugins/dev-team/hooks/pre-commit-knowledge-index.sh 2>&1"
  [ "$status" -eq 2 ]
  [[ "$output" == *"knowledge/index.json is stale"* ]]
}

# ---------------------------------------------------------------------------
# --no-verify bypass works (shared detection)
# ---------------------------------------------------------------------------

@test "bypass: --no-verify is allowed even when index is stale" {
  cd "$BATS_TMPDIR_CASE"
  echo "## New" >> plugins/dev-team/knowledge/foo.md
  echo "Body." >> plugins/dev-team/knowledge/foo.md
  git add plugins/dev-team/knowledge/foo.md

  local input
  input=$(_bash_input "git commit --no-verify -m foo")
  run bash -c "cd '$BATS_TMPDIR_CASE' && echo '$input' | bash plugins/dev-team/hooks/pre-commit-knowledge-index.sh 2>&1"
  [ "$status" -eq 0 ]
}
