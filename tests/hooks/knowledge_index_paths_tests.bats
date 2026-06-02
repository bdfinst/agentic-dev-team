#!/usr/bin/env bats
# Tests for hooks/lib/knowledge-index-paths.sh — the single source of
# truth for whether a path is part of the indexed corpus.
#
# Three callers source this: the PostToolUse hook, the pre-commit
# sibling hook, and the anchor-citation bats test. A future scope
# change is a one-file edit.

PATHS_LIB="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/lib/knowledge-index-paths.sh"

@test "lib exists and is sourceable" {
  [ -f "$PATHS_LIB" ]
  run bash -c "source '$PATHS_LIB' && echo OK"
  [ "$status" -eq 0 ]
  [ "$output" = "OK" ]
}

@test "CORPUS_REGEX is exported and non-empty" {
  run bash -c "source '$PATHS_LIB' && echo \"\$CORPUS_REGEX\""
  [ "$status" -eq 0 ]
  [ -n "$output" ]
}

@test "_is_corpus_path matches knowledge top-level markdown" {
  run bash -c "source '$PATHS_LIB' && _is_corpus_path 'plugins/agentic-dev-team/knowledge/owasp-detection.md'"
  [ "$status" -eq 0 ]
}

@test "_is_corpus_path matches skills SKILL.md" {
  run bash -c "source '$PATHS_LIB' && _is_corpus_path 'plugins/agentic-dev-team/skills/specs/SKILL.md'"
  [ "$status" -eq 0 ]
}

@test "_is_corpus_path rejects knowledge/schemas subdirectory" {
  run bash -c "source '$PATHS_LIB' && _is_corpus_path 'plugins/agentic-dev-team/knowledge/schemas/foo.json'"
  [ "$status" -eq 1 ]
}

@test "_is_corpus_path rejects knowledge/schemas .md file" {
  # A markdown file inside knowledge/schemas/ is still out of scope.
  run bash -c "source '$PATHS_LIB' && _is_corpus_path 'plugins/agentic-dev-team/knowledge/schemas/notes.md'"
  [ "$status" -eq 1 ]
}

@test "_is_corpus_path rejects agent files" {
  run bash -c "source '$PATHS_LIB' && _is_corpus_path 'plugins/agentic-dev-team/agents/security-review.md'"
  [ "$status" -eq 1 ]
}

@test "_is_corpus_path rejects command files" {
  run bash -c "source '$PATHS_LIB' && _is_corpus_path 'plugins/agentic-dev-team/commands/code-review.md'"
  [ "$status" -eq 1 ]
}

@test "_is_corpus_path rejects docs/ files" {
  run bash -c "source '$PATHS_LIB' && _is_corpus_path 'plugins/agentic-dev-team/docs/agent-architecture.md'"
  [ "$status" -eq 1 ]
}

@test "_is_corpus_path rejects non-markdown corpus paths" {
  run bash -c "source '$PATHS_LIB' && _is_corpus_path 'plugins/agentic-dev-team/knowledge/index.json'"
  [ "$status" -eq 1 ]
}

@test "_is_corpus_path rejects unrelated files" {
  run bash -c "source '$PATHS_LIB' && _is_corpus_path 'README.md'"
  [ "$status" -eq 1 ]
  run bash -c "source '$PATHS_LIB' && _is_corpus_path 'plans/foo.md'"
  [ "$status" -eq 1 ]
}

@test "CORPUS_REGEX matches the same paths _is_corpus_path matches" {
  # The regex and function must stay in sync.
  run bash -c "source '$PATHS_LIB' && echo 'plugins/agentic-dev-team/knowledge/owasp-detection.md' | grep -E \"\$CORPUS_REGEX\""
  [ "$status" -eq 0 ]
  run bash -c "source '$PATHS_LIB' && echo 'plugins/agentic-dev-team/skills/specs/SKILL.md' | grep -E \"\$CORPUS_REGEX\""
  [ "$status" -eq 0 ]
  run bash -c "source '$PATHS_LIB' && echo 'plugins/agentic-dev-team/knowledge/schemas/foo.md' | grep -E \"\$CORPUS_REGEX\""
  [ "$status" -ne 0 ]
}
