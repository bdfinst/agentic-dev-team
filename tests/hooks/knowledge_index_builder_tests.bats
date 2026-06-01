#!/usr/bin/env bats
# Tests for hooks/lib/build-knowledge-index.sh — the knowledge index builder.
#
# Tests use the env-var seams (KNOWLEDGE_INDEX_CORPUS_ROOTS,
# KNOWLEDGE_INDEX_OUTPUT) to isolate from the real plugin tree. These
# seams are TEST-ONLY and never used in production.

BUILDER="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh"

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  # Build a minimal fixture corpus mirroring the real layout. The env-var
  # injection points at this tempdir so the test never touches the real
  # plugin source.
  mkdir -p "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/knowledge"
  mkdir -p "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/skills/baz"
  cat > "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/knowledge/foo.md" <<'EOF'
# File Title

## Bar

The Bar section explains how Bar works.
EOF
  cat > "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/skills/baz/SKILL.md" <<'EOF'
# Baz Skill

## Qux

The Qux pattern handles the Qux concern.
EOF
  export KNOWLEDGE_INDEX_CORPUS_ROOTS="$BATS_TMPDIR_CASE/plugins/agentic-dev-team"
  export KNOWLEDGE_INDEX_OUTPUT="$BATS_TMPDIR_CASE/index.json"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset KNOWLEDGE_INDEX_CORPUS_ROOTS KNOWLEDGE_INDEX_OUTPUT
}

# ---------------------------------------------------------------------------
# Step 1 — happy path
# ---------------------------------------------------------------------------

@test "builder produces valid JSON output" {
  bash "$BUILDER"
  run jq -e . "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
}

@test "builder includes both corpus files as top-level keys" {
  bash "$BUILDER"
  run jq -r 'keys | sort | join(",")' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"plugins/agentic-dev-team/knowledge/foo.md"* ]]
  [[ "$output" == *"plugins/agentic-dev-team/skills/baz/SKILL.md"* ]]
}

@test "builder uses repo-relative paths (not absolute)" {
  bash "$BUILDER"
  # No absolute path components.
  run jq -r 'keys[]' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [[ "$output" != *"$BATS_TMPDIR_CASE"* ]]
  [[ "$output" != /* ]]
}

@test "foo.md → Bar entry has exactly summary + anchor (no other fields)" {
  bash "$BUILDER"
  run jq -r '.["plugins/agentic-dev-team/knowledge/foo.md"]["Bar"] | keys | sort | join(",")' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [ "$output" = "anchor,summary" ]
}

@test "summary length >= 8 characters" {
  bash "$BUILDER"
  local summary
  summary=$(jq -r '.["plugins/agentic-dev-team/knowledge/foo.md"]["Bar"].summary' "$KNOWLEDGE_INDEX_OUTPUT")
  [ "${#summary}" -ge 8 ]
}

@test "anchor matches GitHub-style slug regex" {
  bash "$BUILDER"
  local anchor
  anchor=$(jq -r '.["plugins/agentic-dev-team/knowledge/foo.md"]["Bar"].anchor' "$KNOWLEDGE_INDEX_OUTPUT")
  [ "$anchor" = "bar" ]
  [[ "$anchor" =~ ^[a-z0-9][a-z0-9-]*[a-z0-9]?$ ]]
}

# ---------------------------------------------------------------------------
# Step 2 — H2/H3 + source-position ordering + slug disambiguation
# ---------------------------------------------------------------------------

@test "step2: H2 and H3 sections appear in source order (not alphabetical)" {
  cat > "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/knowledge/foo.md" <<'EOF'
# File Title

## Zebra
Body of Zebra section.

### Sub
Body of Sub heading under Zebra.

## Alpha
Body of Alpha section.
EOF
  bash "$BUILDER"
  run jq -r '.["plugins/agentic-dev-team/knowledge/foo.md"] | keys_unsorted | join(",")' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [ "$output" = "Zebra,Sub,Alpha" ]
}

@test "step2: H1 file title is not indexed" {
  cat > "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/knowledge/foo.md" <<'EOF'
# File Title

## Bar
Body.
EOF
  bash "$BUILDER"
  run jq -r '.["plugins/agentic-dev-team/knowledge/foo.md"] | keys[]' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [[ "$output" != *"File Title"* ]]
}

@test "step2: H4 headers are not indexed" {
  cat > "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/knowledge/foo.md" <<'EOF'
# File Title

## Bar
Body of Bar.

#### Deep
Body of Deep.
EOF
  bash "$BUILDER"
  run jq -r '.["plugins/agentic-dev-team/knowledge/foo.md"] | keys[]' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [[ "$output" != *"Deep"* ]]
}

@test "step2: H3 anchors match the same GitHub-style slug regex" {
  cat > "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/knowledge/foo.md" <<'EOF'
# File

## Bar
Body.

### Sub Heading With Spaces
Body of sub.
EOF
  bash "$BUILDER"
  local anchor
  anchor=$(jq -r '.["plugins/agentic-dev-team/knowledge/foo.md"]["Sub Heading With Spaces"].anchor' "$KNOWLEDGE_INDEX_OUTPUT")
  [ "$anchor" = "sub-heading-with-spaces" ]
  [[ "$anchor" =~ ^[a-z0-9][a-z0-9-]*[a-z0-9]?$ ]]
}

@test "step2: duplicate section names get disambiguating suffixes" {
  cat > "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/knowledge/foo.md" <<'EOF'
# File

## Overview
First overview.

## Overview
Second overview.
EOF
  bash "$BUILDER"
  # Section keys must be distinct since duplicates aren't valid JSON keys.
  # The builder must rename the second to "Overview (2)" or similar AND
  # produce anchors `overview` and `overview-1`.
  local keys
  keys=$(jq -r '.["plugins/agentic-dev-team/knowledge/foo.md"] | keys_unsorted | join(",")' "$KNOWLEDGE_INDEX_OUTPUT")
  # Two distinct keys (whatever the rename strategy)
  local count
  count=$(echo "$keys" | tr ',' '\n' | wc -l | tr -d ' ')
  [ "$count" = "2" ]
  # Anchors must be unique within file and follow the GitHub disambiguation.
  local anchors
  anchors=$(jq -r '.["plugins/agentic-dev-team/knowledge/foo.md"][].anchor' "$KNOWLEDGE_INDEX_OUTPUT" | sort)
  expected="$(printf 'overview\noverview-1')"
  [ "$anchors" = "$expected" ]
}

@test "step2: multiple H2 sections in a single file all appear" {
  cat > "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/knowledge/foo.md" <<'EOF'
# File

## First
Body of first.

## Second
Body of second.

## Third
Body of third.
EOF
  bash "$BUILDER"
  run jq -r '.["plugins/agentic-dev-team/knowledge/foo.md"] | keys | length' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [ "$output" = "3" ]
}

@test "no other top-level keys appear" {
  # An extra file outside the corpus must not appear in the index.
  mkdir -p "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/agents"
  cat > "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/agents/some-agent.md" <<'EOF'
# Some Agent
## Section
Body.
EOF
  bash "$BUILDER"
  run jq -r 'keys[]' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [[ "$output" != *"agents/some-agent.md"* ]]
}
