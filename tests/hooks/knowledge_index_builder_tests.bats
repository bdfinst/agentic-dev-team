#!/usr/bin/env bats
# Tests for hooks/lib/build-knowledge-index.sh — the knowledge index builder.
#
# Tests use the env-var seams (KNOWLEDGE_INDEX_CORPUS_ROOTS,
# KNOWLEDGE_INDEX_OUTPUT) to isolate from the real plugin tree. These
# seams are TEST-ONLY and never used in production.

BUILDER="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/build-knowledge-index.sh"

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  # Build a minimal fixture corpus mirroring the real layout. The env-var
  # injection points at this tempdir so the test never touches the real
  # plugin source.
  mkdir -p "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge"
  mkdir -p "$BATS_TMPDIR_CASE/plugins/dev-team/skills/baz"
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
# File Title

## Bar

The Bar section explains how Bar works.
EOF
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/skills/baz/SKILL.md" <<'EOF'
# Baz Skill

## Qux

The Qux pattern handles the Qux concern.
EOF
  export KNOWLEDGE_INDEX_CORPUS_ROOTS="$BATS_TMPDIR_CASE/plugins/dev-team"
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
  [[ "$output" == *"plugins/dev-team/knowledge/foo.md"* ]]
  [[ "$output" == *"plugins/dev-team/skills/baz/SKILL.md"* ]]
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
  run jq -r '.["plugins/dev-team/knowledge/foo.md"]["Bar"] | keys | sort | join(",")' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [ "$output" = "anchor,summary" ]
}

@test "summary length >= 8 characters" {
  bash "$BUILDER"
  local summary
  summary=$(jq -r '.["plugins/dev-team/knowledge/foo.md"]["Bar"].summary' "$KNOWLEDGE_INDEX_OUTPUT")
  [ "${#summary}" -ge 8 ]
}

@test "anchor matches GitHub-style slug regex" {
  bash "$BUILDER"
  local anchor
  anchor=$(jq -r '.["plugins/dev-team/knowledge/foo.md"]["Bar"].anchor' "$KNOWLEDGE_INDEX_OUTPUT")
  [ "$anchor" = "bar" ]
  [[ "$anchor" =~ ^[a-z0-9][a-z0-9-]*[a-z0-9]$ ]]
}

# ---------------------------------------------------------------------------
# Step 2 — H2/H3 + source-position ordering + slug disambiguation
# ---------------------------------------------------------------------------

@test "step2: H2 and H3 sections appear in source order (not alphabetical)" {
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
# File Title

## Zebra
Body of Zebra section.

### Sub
Body of Sub heading under Zebra.

## Alpha
Body of Alpha section.
EOF
  bash "$BUILDER"
  run jq -r '.["plugins/dev-team/knowledge/foo.md"] | keys_unsorted | join(",")' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [ "$output" = "Zebra,Sub,Alpha" ]
}

@test "step2: H1 file title is not indexed" {
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
# File Title

## Bar
Body.
EOF
  bash "$BUILDER"
  run jq -r '.["plugins/dev-team/knowledge/foo.md"] | keys[]' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [[ "$output" != *"File Title"* ]]
}

@test "step2: H4 headers are not indexed" {
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
# File Title

## Bar
Body of Bar.

#### Deep
Body of Deep.
EOF
  bash "$BUILDER"
  run jq -r '.["plugins/dev-team/knowledge/foo.md"] | keys[]' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [[ "$output" != *"Deep"* ]]
}

@test "step2: H3 anchors match the same GitHub-style slug regex" {
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
# File

## Bar
Body.

### Sub Heading With Spaces
Body of sub.
EOF
  bash "$BUILDER"
  local anchor
  anchor=$(jq -r '.["plugins/dev-team/knowledge/foo.md"]["Sub Heading With Spaces"].anchor' "$KNOWLEDGE_INDEX_OUTPUT")
  [ "$anchor" = "sub-heading-with-spaces" ]
  [[ "$anchor" =~ ^[a-z0-9][a-z0-9-]*[a-z0-9]$ ]]
}

@test "step2: duplicate section names get disambiguating suffixes" {
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
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
  keys=$(jq -r '.["plugins/dev-team/knowledge/foo.md"] | keys_unsorted | join(",")' "$KNOWLEDGE_INDEX_OUTPUT")
  # Two distinct keys (whatever the rename strategy)
  local count
  count=$(echo "$keys" | tr ',' '\n' | wc -l | tr -d ' ')
  [ "$count" = "2" ]
  # Anchors must be unique within file and follow the GitHub disambiguation.
  local anchors
  anchors=$(jq -r '.["plugins/dev-team/knowledge/foo.md"][].anchor' "$KNOWLEDGE_INDEX_OUTPUT" | sort)
  expected="$(printf 'overview\noverview-1')"
  [ "$anchors" = "$expected" ]
}

@test "step2: multiple H2 sections in a single file all appear" {
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
# File

## First
Body of first.

## Second
Body of second.

## Third
Body of third.
EOF
  bash "$BUILDER"
  run jq -r '.["plugins/dev-team/knowledge/foo.md"] | keys | length' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [ "$output" = "3" ]
}

# ---------------------------------------------------------------------------
# Step 3 — determinism + lexicographic file ordering
# ---------------------------------------------------------------------------

@test "step3: two rebuilds produce byte-identical output" {
  bash "$BUILDER"
  cp "$KNOWLEDGE_INDEX_OUTPUT" "$BATS_TMPDIR_CASE/first.json"
  bash "$BUILDER"
  cmp "$BATS_TMPDIR_CASE/first.json" "$KNOWLEDGE_INDEX_OUTPUT"
}

@test "step3: top-level file keys appear in lexicographic order" {
  # Create fixture files in deliberately non-alphabetical creation order.
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/zoo.md" <<'EOF'
# Z
## Bar
Body.
EOF
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/alpha.md" <<'EOF'
# A
## Bar
Body.
EOF
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/mid.md" <<'EOF'
# M
## Bar
Body.
EOF
  bash "$BUILDER"
  run jq -r 'keys_unsorted | join("\n")' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  # All knowledge files must precede the skills file, and within each
  # group the order must be lexicographic.
  local sorted
  sorted=$(echo "$output" | LC_ALL=C sort)
  [ "$output" = "$sorted" ]
}

@test "step3: index contains no timestamp / generated_at / build_id fields" {
  bash "$BUILDER"
  # Search the raw JSON file for forbidden field markers.
  ! grep -E '"(generated_at|timestamp|build_id|updated|created_at|date)"' "$KNOWLEDGE_INDEX_OUTPUT"
  # And no ISO-8601-shaped value lurking anywhere.
  ! grep -E '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}' "$KNOWLEDGE_INDEX_OUTPUT"
}

# ---------------------------------------------------------------------------
# Step 4 — summary extraction body-source precedence (Group A)
# ---------------------------------------------------------------------------

@test "step4: body starting with a code fence — summary is first non-code line" {
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
# File

## Bar

```bash
echo hello
```

The explanation that follows the code block is the summary.

EOF
  bash "$BUILDER"
  local summary
  summary=$(jq -r '.["plugins/dev-team/knowledge/foo.md"]["Bar"].summary' "$KNOWLEDGE_INDEX_OUTPUT")
  [ "$summary" = "The explanation that follows the code block is the summary." ]
}

@test "step4: body that is only a bullet list — summary is first bullet text" {
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
# File

## Bar

- First bullet about the topic.
- Second bullet.
- Third bullet.
EOF
  bash "$BUILDER"
  local summary
  summary=$(jq -r '.["plugins/dev-team/knowledge/foo.md"]["Bar"].summary' "$KNOWLEDGE_INDEX_OUTPUT")
  [ "$summary" = "First bullet about the topic." ]
}

@test "step4: body empty until next sub-header — summary is from child section" {
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
# File

## Bar

### Sub

The first sentence of the sub-section.
EOF
  bash "$BUILDER"
  local summary
  summary=$(jq -r '.["plugins/dev-team/knowledge/foo.md"]["Bar"].summary' "$KNOWLEDGE_INDEX_OUTPUT")
  [ "$summary" = "The first sentence of the sub-section." ]
}

# ---------------------------------------------------------------------------
# Step 4 — sentence-boundary rule (Group B / AC7a)
# ---------------------------------------------------------------------------

_run_sentence_case() {
  # Helper: write a fixture with the given body line(s), build, and
  # echo the resulting summary.
  local body="$1"
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<EOF
# File

## Bar

$body
EOF
  bash "$BUILDER" >/dev/null
  jq -r '.["plugins/dev-team/knowledge/foo.md"]["Bar"].summary' "$KNOWLEDGE_INDEX_OUTPUT"
}

@test "step4 AC7a: clean single sentence with comma" {
  local got
  got=$(_run_sentence_case "Detection patterns for SQL, NoSQL, and ORM injection vectors.")
  [ "$got" = "Detection patterns for SQL, NoSQL, and ORM injection vectors." ]
}

@test "step4 AC7a: e.g. abbreviation does NOT terminate a sentence" {
  local got
  got=$(_run_sentence_case "Frameworks like e.g. Django need careful handling. More follows.")
  [ "$got" = "Frameworks like e.g. Django need careful handling." ]
}

@test "step4 AC7a: single-uppercase initials (J. Doe) do NOT terminate a sentence" {
  local got
  got=$(_run_sentence_case "Authored by J. Doe and others. Reviewed by team.")
  [ "$got" = "Authored by J. Doe and others." ]
}

@test "step4 AC7a: Mr. abbreviation does NOT terminate a sentence" {
  local got
  got=$(_run_sentence_case "Use Mr. Smith's heuristic. Then iterate.")
  [ "$got" = "Use Mr. Smith's heuristic." ]
}

@test "step4 AC7a: vs abbreviation does NOT terminate a sentence" {
  local got
  got=$(_run_sentence_case "Validation, vs. trust assumptions. Always validate.")
  [ "$got" = "Validation, vs. trust assumptions." ]
}

@test "step4 AC7a: 260-char paragraph with no terminator gets truncated with ellipsis" {
  # 270-char string, no '.', '!', or '?' anywhere.
  local body
  body=$(python3 -c "print('word ' * 54)")  # ~270 chars, all whitespace-separated 'word'
  local got
  got=$(_run_sentence_case "$body")
  # Length is at most 241 (240 chars + the ellipsis character)
  # The ellipsis is a single Unicode char (3 bytes in UTF-8), count by char count.
  local len
  len=$(printf '%s' "$got" | python3 -c "import sys; print(len(sys.stdin.read()))")
  [ "$len" -le 241 ]
  [[ "$got" == *"…" ]]
}

@test "step4: section body content containing triple double-quotes is handled" {
  # Regression test for the previous heredoc interpolation bug.
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
# File

## Bar

The docstring like """example""" must not break index generation.
EOF
  bash "$BUILDER"
  run jq -e '.["plugins/dev-team/knowledge/foo.md"]["Bar"]' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
}

@test "step4: every summary in the index ends with a terminator" {
  # Property test: regardless of source variation, summaries must end
  # with one of . ! ? or the truncation ellipsis.
  bash "$BUILDER"
  local bad
  bad=$(jq -r '[.. | objects | select(.summary?) | .summary] | .[]' "$KNOWLEDGE_INDEX_OUTPUT" \
    | grep -vE '[.!?…]$' || true)
  [ -z "$bad" ]
}

@test "step4: sentence that wraps across two lines — first line is captured" {
  # The spec says summary is the first non-blank line under the header.
  # A wrapped sentence is captured up to the line wrap (the line break
  # is the body boundary for the first-pass extractor).
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/knowledge/foo.md" <<'EOF'
# File

## Bar

This is a sentence that wraps onto
a second line of the same paragraph.
EOF
  bash "$BUILDER"
  local summary
  summary=$(jq -r '.["plugins/dev-team/knowledge/foo.md"]["Bar"].summary' "$KNOWLEDGE_INDEX_OUTPUT")
  # The summary must end in a terminator (the truncation ellipsis applies
  # when no terminator is on the captured line).
  [[ "$summary" =~ [.!?…]$ ]]
  # The captured body should contain content from the first line.
  [[ "$summary" == *"This is a sentence that wraps onto"* ]] || [[ "$summary" == *"…" ]]
}

# ---------------------------------------------------------------------------
# Step 5 — --check mode
# ---------------------------------------------------------------------------

@test "step5: --check on a current index exits 0 with zero stdout AND zero stderr" {
  bash "$BUILDER"
  # Capture stdout and stderr separately. AC17a: both must be empty.
  local stdout_file stderr_file
  stdout_file=$(mktemp)
  stderr_file=$(mktemp)
  bash "$BUILDER" --check > "$stdout_file" 2> "$stderr_file"
  local status=$?
  [ "$status" -eq 0 ]
  [ ! -s "$stdout_file" ]
  [ ! -s "$stderr_file" ]
  rm -f "$stdout_file" "$stderr_file"
}

@test "step5: --check on a stale index exits non-zero with unified-diff stderr" {
  bash "$BUILDER"
  # Corrupt the on-disk index by appending content the rebuild won't produce.
  echo '{"junk":"value"}' > "$KNOWLEDGE_INDEX_OUTPUT"
  local stderr_file
  stderr_file=$(mktemp)
  run bash -c "bash '$BUILDER' --check > /dev/null 2> '$stderr_file'"
  [ "$status" -ne 0 ]
  grep -q '^---' "$stderr_file"
  grep -q '^+++' "$stderr_file"
  grep -q '^@@' "$stderr_file"
  rm -f "$stderr_file"
}

@test "step5: --check on a missing index exits non-zero with actionable stderr" {
  bash "$BUILDER"
  rm -f "$KNOWLEDGE_INDEX_OUTPUT"
  local stderr_file
  stderr_file=$(mktemp)
  run bash -c "bash '$BUILDER' --check > /dev/null 2> '$stderr_file'"
  [ "$status" -ne 0 ]
  grep -q 'missing' "$stderr_file"
  rm -f "$stderr_file"
}

@test "step5: --check writes NO file (read-only)" {
  bash "$BUILDER"
  # Snapshot the file tree before --check.
  local before after
  before=$(cd "$BATS_TMPDIR_CASE" && find . -type f | LC_ALL=C sort | xargs shasum -a 256 2>/dev/null | shasum -a 256)
  bash "$BUILDER" --check > /dev/null 2>&1
  after=$(cd "$BATS_TMPDIR_CASE" && find . -type f | LC_ALL=C sort | xargs shasum -a 256 2>/dev/null | shasum -a 256)
  [ "$before" = "$after" ]
}

@test "no other top-level keys appear" {
  # An extra file outside the corpus must not appear in the index.
  mkdir -p "$BATS_TMPDIR_CASE/plugins/dev-team/agents"
  cat > "$BATS_TMPDIR_CASE/plugins/dev-team/agents/some-agent.md" <<'EOF'
# Some Agent
## Section
Body.
EOF
  bash "$BUILDER"
  run jq -r 'keys[]' "$KNOWLEDGE_INDEX_OUTPUT"
  [ "$status" -eq 0 ]
  [[ "$output" != *"agents/some-agent.md"* ]]
}
