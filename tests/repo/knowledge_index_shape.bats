#!/usr/bin/env bats
# + : the shipped knowledge/index.json exists, parses as JSON,
# and contains exactly the in-scope corpus.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
INDEX="$REPO_ROOT/plugins/dev-team/knowledge/index.json"

@test "index file exists and parses as JSON" {
  [ -f "$INDEX" ]
  run jq -e . "$INDEX"
  [ "$status" -eq 0 ]
}

@test "every knowledge/*.md (excluding schemas/) appears as a top-level key" {
  cd "$REPO_ROOT" || return 1
  for f in plugins/dev-team/knowledge/*.md; do
    [ -f "$f" ] || continue
    run jq -e --arg k "$f" 'has($k)' "$INDEX"
    [ "$status" -eq 0 ] || { echo "missing key: $f" >&2; return 1; }
  done
}

@test "every skills/*/SKILL.md appears as a top-level key" {
  cd "$REPO_ROOT" || return 1
  for f in plugins/dev-team/skills/*/SKILL.md; do
    [ -f "$f" ] || continue
    run jq -e --arg k "$f" 'has($k)' "$INDEX"
    [ "$status" -eq 0 ] || { echo "missing key: $f" >&2; return 1; }
  done
}

@test "no file outside the corpus appears as a top-level key" {
  cd "$REPO_ROOT" || return 1
  local bad
  bad=$(jq -r 'keys[]' "$INDEX" | grep -vE '^plugins/dev-team/(knowledge/[^/]+\.md|skills/[^/]+/SKILL\.md)$' || true)
  if [[ -n "$bad" ]]; then
    echo "out-of-corpus keys found:" >&2
    echo "$bad" >&2
    return 1
  fi
}

@test "knowledge/schemas/ subdirectory is excluded" {
  cd "$REPO_ROOT" || return 1
  run jq -r 'keys[]' "$INDEX"
  [[ "$output" != *"knowledge/schemas"* ]]
}

@test "no docs/, agents/, or commands/ paths appear" {
  cd "$REPO_ROOT" || return 1
  run jq -r 'keys[]' "$INDEX"
  [[ "$output" != *"/docs/"* ]]
  [[ "$output" != *"/agents/"* ]]
  [[ "$output" != *"/commands/"* ]]
}
