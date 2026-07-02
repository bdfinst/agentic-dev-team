#!/usr/bin/env bats
# The knowledge-index builder must publish the index ATOMICALLY.
#
# Why: under parallel `bats --jobs`, one test rebuilds the index while
# another reads it. A truncate-then-stream write (`Path.write_text`) leaves
# a window where a concurrent reader observes an empty or partial file and a
# real key looks "missing". The only correct fix for unsynchronized readers
# is an atomic publish: build into a sibling temp file, then rename it over
# the destination. `os.replace` does exactly that — and its observable
# signature is that the destination path's inode is SWAPPED on each rebuild
# (a truncate-in-place keeps the same inode). These tests assert that
# signature deterministically, so we don't depend on catching a timing race.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
BUILDER="$REPO_ROOT/plugins/dev-team/hooks/lib/build_knowledge_index.py"
SENTINEL="plugins/dev-team/knowledge/agent-registry.md"

# Portable inode read (macOS + Linux): `ls -i` prints the inode first.
inode_of() { ls -i "$1" | awk '{print $1}'; }

setup() {
  TMP="$(mktemp -d)"
  OUT="$TMP/index.json"
}

teardown() {
  [ -n "${TMP:-}" ] && rm -rf "$TMP"
}

@test "atomic-publish: a rebuild swaps the index inode (rename, not truncate-in-place)" {
  KNOWLEDGE_INDEX_OUTPUT="$OUT" python3 "$BUILDER"
  local before after
  before="$(inode_of "$OUT")"
  KNOWLEDGE_INDEX_OUTPUT="$OUT" python3 "$BUILDER"
  after="$(inode_of "$OUT")"
  [ "$before" != "$after" ] || {
    echo "inode unchanged ($before): index was rewritten in place, not atomically replaced" >&2
    return 1
  }
}

@test "atomic-publish: the destination is always complete (sentinel present after each rebuild)" {
  KNOWLEDGE_INDEX_OUTPUT="$OUT" python3 "$BUILDER"
  run jq -e --arg k "$SENTINEL" 'has($k)' "$OUT"
  [ "$status" -eq 0 ]
  # A second rebuild must also leave a complete, parseable file behind.
  KNOWLEDGE_INDEX_OUTPUT="$OUT" python3 "$BUILDER"
  run jq -e --arg k "$SENTINEL" 'has($k)' "$OUT"
  [ "$status" -eq 0 ]
}
