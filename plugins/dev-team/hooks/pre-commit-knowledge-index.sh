#!/usr/bin/env bash
# pre-commit-knowledge-index.sh — PreToolUse:Bash hook.
#
# Blocks `git commit` when the working-tree knowledge/index.json does
# not match what a fresh build of the working tree would produce. The
# PostToolUse hook (knowledge-index.sh) keeps the working-tree index
# current on every Edit, so this gate's only purpose is to catch the
# `git add corpus.md` without `git add knowledge/index.json` case.
#
# Comparison surface: working tree (not staged content). The remediation
# message explicitly tells the contributor to run the builder AND `git
# add` the result.
#
# Sibling to hooks/pre-commit-review.sh — both share the `git commit`
# detection helper at hooks/lib/pre-commit-detect.sh and the corpus-path
# helper at hooks/lib/knowledge-index-paths.sh. The two hooks have
# independent concerns (review-pass vs index-freshness); the sibling
# pattern keeps each file single-purpose.
#
# Input:  JSON on stdin (Claude Code PreToolUse:Bash contract).
# Exit 0: Allow the commit (non-commit invocation, --no-verify bypass,
#         no corpus files staged, or index matches working tree).
# Exit 2: Block the commit with a two-line remediation message.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/knowledge-index-paths.sh
source "${HOOK_DIR}/lib/knowledge-index-paths.sh"
# shellcheck source=lib/pre-commit-detect.sh
source "${HOOK_DIR}/lib/pre-commit-detect.sh"
BUILDER="${KNOWLEDGE_INDEX_BUILDER:-${HOOK_DIR}/lib/build-knowledge-index.sh}"

main() {
  local input
  input=$(cat)

  local cmd
  cmd=$(echo "$input" | jq -r '.tool_input.command // ""' 2>/dev/null)

  # Non-commit (or --no-verify bypass) → no-op.
  if ! _is_git_commit_invocation "$cmd"; then
    return 0
  fi

  # List staged files. Filter to corpus files only.
  local staged corpus_staged
  staged=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null || true)
  corpus_staged=""
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if _is_corpus_path "$f"; then
      corpus_staged="${corpus_staged}${f}"$'\n'
    fi
  done <<<"$staged"

  # Nothing in the corpus staged → not our concern.
  if [[ -z "$corpus_staged" ]]; then
    return 0
  fi

  # Working-tree freshness check.
  local stderr_file
  stderr_file=$(mktemp)
  if bash "$BUILDER" --check >/dev/null 2>"$stderr_file"; then
    rm -f "$stderr_file"
    return 0
  fi

  cat >&2 <<'EOF'
knowledge/index.json is stale; the auto-rebuild ran but you must stage the result.

  1. bash plugins/dev-team/hooks/lib/build-knowledge-index.sh
  2. git add plugins/dev-team/knowledge/index.json

Diff (expected vs working tree):
EOF
  cat "$stderr_file" >&2
  rm -f "$stderr_file"
  return 2
}

main
