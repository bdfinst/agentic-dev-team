#!/usr/bin/env bash
# knowledge-index-paths.sh — single source of truth for the indexed corpus.
#
# Sourced (not executed) by three callers:
#   - hooks/knowledge-index.sh                  (PostToolUse regenerator)
#   - hooks/pre-commit-knowledge-index.sh       (pre-commit freshness gate)
#   - tests/agents/agent_knowledge_anchor_tests.bats (anchor-citation gate)
#
# Exports:
#   CORPUS_REGEX — ERE regex matching corpus paths from a file list
#   _is_corpus_path <path> — returns 0 iff the path is in the indexed corpus
#
# The corpus is:
#   - plugins/dev-team/knowledge/*.md         (top-level .md only)
#   - plugins/dev-team/skills/<name>/SKILL.md
#
# Excluded:
#   - plugins/dev-team/knowledge/schemas/**   (json schemas, not docs)
#   - everything else (agents/, commands/, docs/, README.md, etc.)
#
# Anchor: top-level knowledge .md OR <skills-dir>/<one segment>/SKILL.md.
# A leading `(.*\/)?` allows repo-relative or absolute paths.

# ERE form for grep -E.
CORPUS_REGEX='(^|/)plugins/dev-team/(knowledge/[^/]+\.md|skills/[^/]+/SKILL\.md)$'

# _is_corpus_path <path>
# Returns 0 (true) when the path matches the indexed corpus, 1 otherwise.
_is_corpus_path() {
  [[ "$1" =~ /?plugins/dev-team/(knowledge/[^/]+\.md|skills/[^/]+/SKILL\.md)$ ]]
}
