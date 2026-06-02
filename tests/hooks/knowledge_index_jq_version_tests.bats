#!/usr/bin/env bats
# AC24: builder is a single Python process. The shell wrapper exec's
# the Python implementation; jq is no longer required after the
# perf-rewrite.
#
# Renamed from the original jq-version-pin tests; kept the file name
# stable so existing CI workflows don't drift.

BUILDER_SH="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh"
BUILDER_PY="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/lib/build_knowledge_index.py"

@test "AC24: shell wrapper and python implementation both exist" {
  [ -f "$BUILDER_SH" ]
  [ -f "$BUILDER_PY" ]
}

@test "AC24: shell wrapper exec's the python builder (not jq)" {
  # The wrapper must invoke python3 and the .py file. It must NOT
  # invoke jq directly.
  run grep -E "exec[[:space:]]+python3" "$BUILDER_SH"
  [ "$status" -eq 0 ]
  run grep -E "build_knowledge_index\.py" "$BUILDER_SH"
  [ "$status" -eq 0 ]
  # No jq invocations in the wrapper body.
  run grep -E "^[[:space:]]*jq[[:space:]]" "$BUILDER_SH"
  [ "$status" -ne 0 ]
}

@test "AC24: python builder runs standalone (returns valid JSON)" {
  local tmp out
  tmp=$(mktemp -d)
  out="$tmp/index.json"
  mkdir -p "$tmp/plugins/agentic-dev-team/knowledge"
  cat > "$tmp/plugins/agentic-dev-team/knowledge/foo.md" <<'EOF'
# F
## Bar
Body sentence.
EOF
  KNOWLEDGE_INDEX_CORPUS_ROOTS="$tmp/plugins/agentic-dev-team" \
    KNOWLEDGE_INDEX_OUTPUT="$out" \
    python3 "$BUILDER_PY"
  run jq -e . "$out"
  [ "$status" -eq 0 ]
  rm -rf "$tmp"
}
