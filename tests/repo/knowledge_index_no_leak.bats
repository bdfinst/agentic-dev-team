#!/usr/bin/env bats
# AC21: building the knowledge index must leave no temp-file leak — the
# builder publishes atomically (temp file + rename), and on success the
# only artifact in the output directory is the index itself.
#
# This builds into an ISOLATED output (the KNOWLEDGE_INDEX_OUTPUT test seam)
# rather than rewriting the canonical plugins/dev-team/knowledge/index.json
# in place. That keeps the test parallel-safe under `bats --jobs` (no shared
# mutable repo file that concurrent readers might catch mid-write) and lets
# it run unconditionally instead of skipping whenever the working tree is
# dirty. Correctness of the real corpus build is cross-checked against the
# committed index byte-for-byte.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
BUILDER="$REPO_ROOT/plugins/dev-team/hooks/lib/build-knowledge-index.sh"
COMMITTED_INDEX="$REPO_ROOT/plugins/dev-team/knowledge/index.json"

setup() {
  TMP="$(mktemp -d)"
  OUT="$TMP/index.json"
}

teardown() {
  [ -n "${TMP:-}" ] && rm -rf "$TMP"
}

@test "AC21: a rebuild leaves no temp or partial files beside the index" {
  # Default corpus roots (the real plugin tree) → output diverted to TMP.
  KNOWLEDGE_INDEX_OUTPUT="$OUT" bash "$BUILDER"
  # On a clean publish the temp file has been renamed onto the index; the
  # only thing left in the directory is the index itself.
  run bash -c "ls -A '$TMP'"
  [ "$status" -eq 0 ]
  [ "$output" = "index.json" ]
}

@test "AC21: the diverted build is byte-identical to the committed index" {
  KNOWLEDGE_INDEX_OUTPUT="$OUT" bash "$BUILDER"
  run diff -u "$COMMITTED_INDEX" "$OUT"
  [ "$status" -eq 0 ]
}
