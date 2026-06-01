#!/usr/bin/env bats
# AC1 + AC6: the shipped knowledge/index.json exists, parses as JSON,
# and contains exactly the in-scope corpus.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
INDEX="$REPO_ROOT/plugins/agentic-dev-team/knowledge/index.json"

@test "AC1: index file exists and parses as JSON" {
  [ -f "$INDEX" ]
  run jq -e . "$INDEX"
  [ "$status" -eq 0 ]
}

@test "AC6: every knowledge/*.md (excluding schemas/) appears as a top-level key" {
  cd "$REPO_ROOT"
  for f in plugins/agentic-dev-team/knowledge/*.md; do
    [ -f "$f" ] || continue
    run jq -e --arg k "$f" 'has($k)' "$INDEX"
    [ "$status" -eq 0 ] || { echo "missing key: $f" >&2; return 1; }
  done
}

@test "AC6: every skills/*/SKILL.md appears as a top-level key" {
  cd "$REPO_ROOT"
  for f in plugins/agentic-dev-team/skills/*/SKILL.md; do
    [ -f "$f" ] || continue
    run jq -e --arg k "$f" 'has($k)' "$INDEX"
    [ "$status" -eq 0 ] || { echo "missing key: $f" >&2; return 1; }
  done
}

@test "AC6: no file outside the corpus appears as a top-level key" {
  cd "$REPO_ROOT"
  local bad
  bad=$(jq -r 'keys[]' "$INDEX" | grep -vE '^plugins/agentic-dev-team/(knowledge/[^/]+\.md|skills/[^/]+/SKILL\.md)$' || true)
  if [[ -n "$bad" ]]; then
    echo "out-of-corpus keys found:" >&2
    echo "$bad" >&2
    return 1
  fi
}

@test "AC6: knowledge/schemas/ subdirectory is excluded" {
  cd "$REPO_ROOT"
  run jq -r 'keys[]' "$INDEX"
  [[ "$output" != *"knowledge/schemas"* ]]
}

@test "AC6: no docs/, agents/, or commands/ paths appear" {
  cd "$REPO_ROOT"
  run jq -r 'keys[]' "$INDEX"
  [[ "$output" != *"/docs/"* ]]
  [[ "$output" != *"/agents/"* ]]
  [[ "$output" != *"/commands/"* ]]
}
